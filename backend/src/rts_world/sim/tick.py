"""Region tick orchestrator.

The contract (roadmap §5.1):

    one wide SELECT (load) -> pure-Python simulate() -> one bulk UPDATE
    plus one bulk INSERT into world_events, all in one BEGIN/COMMIT.

This file is the only thing that knows the order is load -> systems -> write.
``regions.py`` owns the SQL; ``systems/`` owns the behaviour. ``tick.py`` just
glues them together and handles the things that apply to every tick (paused
check, world clock advance, last_tick_at bump, error handling, timing).
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import psycopg

from ..db.db import get_connection
from . import regions as regions_repo
from .clock import advance_clock, read_clock
from .state import PendingEvent, RegionState, TickContext
from .systems import System, default_systems


log = logging.getLogger(__name__)


@dataclass
class TickResult:
    """What happened during one tick. Returned for logging / tests."""

    region_id: int
    region_name: str
    skipped_reason: str | None = None
    entities_loaded: int = 0
    relationships_loaded: int = 0
    events_emitted: int = 0
    relationships_updated: int = 0
    duration_ms: float = 0.0
    game_day: int = 0
    game_tick: int = 0

    @property
    def skipped(self) -> bool:
        return self.skipped_reason is not None


def tick_region(
    region_id: int,
    *,
    conn: psycopg.Connection | None = None,
    systems: Sequence[System] | None = None,
    rng_seed: int | None = None,
) -> TickResult:
    """Tick one region. The unit of scheduling AND of transaction.

    If ``conn`` is None we open and close our own — that's the normal path
    used by the scheduler. Tests pass a connection in to keep everything in
    one cleanup scope.

    If the region is paused (Unreal owns it), this is a no-op.
    """
    own_conn = False
    if conn is None:
        conn = get_connection()
        own_conn = True

    started = time.perf_counter()
    now = datetime.now(timezone.utc)

    try:
        # 1. Load. Cheap region row first so we can short-circuit pauses
        #    without paying for the full working-set load.
        region = regions_repo.get_region(conn, region_id)
        if region is None:
            return TickResult(
                region_id=region_id,
                region_name="?",
                skipped_reason="not_found",
            )
        if bool(region["paused"]):
            return TickResult(
                region_id=region_id,
                region_name=str(region["name"]),
                skipped_reason="paused",
            )

        state = regions_repo.load_region_state(conn, region_id)
        # ``load_region_state`` re-fetches the region row. It can't be None
        # here because we just confirmed it exists, but keep the guard
        # explicit for the type checker.
        if state is None:
            return TickResult(
                region_id=region_id,
                region_name=str(region["name"]),
                skipped_reason="not_found",
            )

        # 2. Build per-tick context. Reading the clock here means systems see
        #    the value *before* this tick's advance — the new value reflects
        #    "after tick N". That keeps tick numbering monotonic.
        clock = read_clock(conn)
        ctx = TickContext(
            region_id=region_id,
            now=now,
            game_day=clock.game_day,
            game_tick=clock.game_tick,
            rng=random.Random(
                rng_seed
                if rng_seed is not None
                # Deterministic but well-mixed default: combine region id with
                # the in-game tick so each region has its own stream.
                else hash((region_id, clock.game_tick)) & 0xFFFFFFFF
            ),
        )

        # 3. Run systems. Pure Python; no DB.
        chosen_systems = systems if systems is not None else default_systems()
        events: list[PendingEvent] = []
        for sys in chosen_systems:
            events.extend(sys(state, ctx))

        # 4. Write. Single round-trip-set, single BEGIN/COMMIT.
        write_summary = regions_repo.write_region_state(conn, state, events, now=now)
        new_clock = advance_clock(conn)
        conn.commit()

        return TickResult(
            region_id=region_id,
            region_name=str(state.region["name"]),
            entities_loaded=len(state.entities),
            relationships_loaded=len(state.relationships),
            events_emitted=write_summary["events_inserted"],
            relationships_updated=write_summary["relationships_updated"],
            duration_ms=(time.perf_counter() - started) * 1000.0,
            game_day=new_clock.game_day,
            game_tick=new_clock.game_tick,
        )

    except Exception:
        # Long transactions are a footgun (roadmap §10). On any failure roll
        # back so we never leave a partial tick in flight.
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            log.exception("rollback failed for region %s", region_id)
        log.exception("tick_region(%s) failed", region_id)
        raise
    finally:
        if own_conn:
            conn.close()

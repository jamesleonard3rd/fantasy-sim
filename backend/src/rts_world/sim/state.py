"""In-memory data shapes for one region tick.

These types are pure Python — no DB, no I/O. Systems read and mutate
``RegionState`` and return ``PendingEvent`` rows. The DB layer (``regions.py``,
``events.py``, ``clock.py``) is the only thing that knows about Postgres.

Entities are kept as dicts on purpose. The roadmap (§5.3) explicitly rejects
instantiating Entity objects per tick — column-oriented dicts (or numpy
columns later) are dramatically faster and trivially serialisable.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ---------- pending writes from a tick ----------

@dataclass
class PendingEvent:
    """Append to ``world_events`` at the end of a tick.

    ``region_id`` is filled in by the writer from the tick's region, so systems
    don't have to thread it through every call.
    """

    kind: str
    subject_entity_id: int | None = None
    target_entity_id: int | None = None
    payload: dict[str, Any] | None = None


# ---------- working set for one region tick ----------

@dataclass
class RegionState:
    """Everything one region tick reads or writes, held in memory.

    Loaded by ``regions.load_region_state`` with one wide SELECT per table.
    Mutated in place by systems. Persisted by ``regions.write_region_state``
    with one ``executemany`` per changed table.

    The ``dirty_*`` sets track which rows changed so the writer can issue
    minimal UPDATEs instead of rewriting the whole working set.
    """

    region: dict[str, Any]
    entities: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)

    # Indices that systems can rely on; rebuilt by load_region_state.
    entities_by_id: dict[int, dict[str, Any]] = field(default_factory=dict)

    # Mutation tracking. Systems should add ids/keys here when they mutate
    # the corresponding rows so the write path knows what to flush.
    dirty_entity_ids: set[int] = field(default_factory=set)
    dirty_relationship_keys: set[tuple[int, int]] = field(default_factory=set)

    @property
    def region_id(self) -> int:
        return int(self.region["id"])

    def mark_entity_dirty(self, entity_id: int) -> None:
        self.dirty_entity_ids.add(int(entity_id))

    def mark_relationship_dirty(self, subject_id: int, target_id: int) -> None:
        self.dirty_relationship_keys.add((int(subject_id), int(target_id)))


# ---------- per-tick context shared by all systems ----------

@dataclass
class TickContext:
    """Read-only-ish per-tick scratchpad passed to every system.

    ``rng`` is a per-tick ``random.Random`` so simulations are deterministic
    when seeded. ``now`` is wall clock at tick start (used for ``last_tick_at``
    bookkeeping). ``game_day`` / ``game_tick`` come from ``world_clock`` so
    systems can reason about in-game time without consulting the wall clock.
    """

    region_id: int
    now: datetime
    game_day: int
    game_tick: int
    rng: random.Random

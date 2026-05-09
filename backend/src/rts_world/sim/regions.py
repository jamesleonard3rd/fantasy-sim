"""Region repository: load and write the working set for one region tick.

This is the only place where per-entity component tables are read or
written by the sim. The contract (roadmap §5.1) is:

    * load_region_state: one wide SELECT per relevant table, filtered by
      region_id.
    * write_region_state: one executemany per dirty table + one
      executemany INSERT into world_events.
    * The caller wraps both in a single BEGIN/COMMIT.

Helpers for region lifecycle live here too (query_due_regions, set_paused,
seed_regions_with_assignment) so all region-table SQL is in one file.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import psycopg

from .events import bulk_insert_events
from .state import PendingEvent, RegionState


# ---------- region row helpers ----------

def get_region(conn: psycopg.Connection, region_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, kind, tick_interval_seconds,
                   last_tick_at, paused
              FROM regions
             WHERE id = %s
            """,
            (region_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": int(row[0]),
            "name": row[1],
            "kind": row[2],
            "tick_interval_seconds": int(row[3]),
            "last_tick_at": row[4],
            "paused": bool(row[5]),
        }


def query_due_regions(
    conn: psycopg.Connection, *, now: datetime
) -> list[dict[str, Any]]:
    """Regions that are unpaused AND whose next tick is due at or before ``now``.

    Used by the scheduler on startup and during periodic refresh. The runtime
    loop normally pops directly from its in-memory heap; this is the
    bootstrap/refresh path.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, tick_interval_seconds, last_tick_at
              FROM regions
             WHERE paused = FALSE
               AND (last_tick_at IS NULL
                    OR last_tick_at + (tick_interval_seconds * INTERVAL '1 second') <= %s)
             ORDER BY last_tick_at NULLS FIRST
            """,
            (now,),
        )
        return [
            {
                "id": int(r[0]),
                "name": r[1],
                "tick_interval_seconds": int(r[2]),
                "last_tick_at": r[3],
            }
            for r in cur.fetchall()
        ]


def list_unpaused_regions(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """All unpaused regions, with the fields the scheduler needs to schedule them."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, tick_interval_seconds, last_tick_at
              FROM regions
             WHERE paused = FALSE
             ORDER BY id
            """
        )
        return [
            {
                "id": int(r[0]),
                "name": r[1],
                "tick_interval_seconds": int(r[2]),
                "last_tick_at": r[3],
            }
            for r in cur.fetchall()
        ]


def set_paused(conn: psycopg.Connection, region_id: int, paused: bool) -> None:
    """Authority handoff (roadmap §5.5). Unreal flips this on region entry/exit.

    The background sim should never write to regions where ``paused = TRUE``.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE regions SET paused = %s WHERE id = %s",
            (paused, region_id),
        )


def update_last_tick_at(
    conn: psycopg.Connection, region_id: int, now: datetime
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE regions SET last_tick_at = %s WHERE id = %s",
            (now, region_id),
        )


# ---------- working set load ----------

def load_region_state(conn: psycopg.Connection, region_id: int) -> RegionState | None:
    """Load every per-entity row this region needs into memory.

    One SELECT per table; no joins required because the sim works
    column-oriented. The result is purely in-memory dicts/lists ready for
    pure-Python systems to mutate.

    Returns ``None`` if the region doesn't exist; a tick of an unknown
    region is a no-op.
    """
    region = get_region(conn, region_id)
    if region is None:
        return None

    state = RegionState(region=region)

    with conn.cursor() as cur:
        # Entities currently zoned to this region. The wide SELECT pattern: one
        # round-trip, no per-entity follow-ups.
        cur.execute(
            """
            SELECT e.id, e.name, e.type, e.race_id, e.subrace_id, e.created_at
              FROM entities e
              JOIN entity_zones z ON z.entity_id = e.id
             WHERE z.region_id = %s
             ORDER BY e.id
            """,
            (region_id,),
        )
        for row in cur.fetchall():
            ent: dict[str, object] = {
                "id": int(row[0]),
                "name": row[1],
                "type": row[2],
                "race_id": int(row[3]),
                "subrace_id": int(row[4]) if row[4] is not None else None,
                "created_at": row[5],
            }
            state.entities.append(ent)
            state.entities_by_id[int(row[0])] = ent

        # Relationships among entities currently in this region. We deliberately
        # only load rows where BOTH endpoints are in-region; cross-region
        # relationships are a separate concern (faction politics handles that).
        if state.entities_by_id:
            ids = tuple(state.entities_by_id.keys())
            cur.execute(
                """
                SELECT subject_entity_id, target_entity_id, opinion, last_updated
                  FROM relationships
                 WHERE subject_entity_id = ANY(%s)
                   AND target_entity_id  = ANY(%s)
                """,
                (list(ids), list(ids)),
            )
            for row in cur.fetchall():
                state.relationships.append(
                    {
                        "subject_entity_id": int(row[0]),
                        "target_entity_id": int(row[1]),
                        "opinion": int(row[2]),
                        "last_updated": row[3],
                    }
                )

    return state


# ---------- working set write ----------

def write_region_state(
    conn: psycopg.Connection,
    state: RegionState,
    events: Iterable[PendingEvent],
    *,
    now: datetime,
) -> dict[str, int]:
    """Flush dirty rows and emitted events for a region in one round-trip-set.

    Returns a small summary dict used by the runner CLI for reporting.
    All writes go through executemany; never a per-entity loop.
    """
    summary = {
        "entities_updated": 0,
        "relationships_updated": 0,
        "events_inserted": 0,
    }

    region_id = state.region_id

    # Relationships: bulk update only the dirty ones.
    if state.dirty_relationship_keys:
        # Build a (subject, target, opinion) tuple list from the in-memory rows.
        by_key = {
            (int(r["subject_entity_id"]), int(r["target_entity_id"])): r
            for r in state.relationships
        }
        rows = []
        for key in state.dirty_relationship_keys:
            row = by_key.get(key)
            if row is None:
                continue
            rows.append((int(row["opinion"]), key[0], key[1]))
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    UPDATE relationships
                       SET opinion = %s,
                           last_updated = NOW()
                     WHERE subject_entity_id = %s
                       AND target_entity_id  = %s
                    """,
                    rows,
                )
            summary["relationships_updated"] = len(rows)

    # Entities: nothing to flush yet at the MVP level (no mutable columns
    # touched by current systems). Reserved hook for needs/goals once those
    # land and add per-entity scalar columns.
    if state.dirty_entity_ids:
        # Placeholder: future systems will UPDATE entities here in one
        # executemany. For now this branch is unreachable because no MVP
        # system marks entities dirty.
        pass

    summary["events_inserted"] = bulk_insert_events(conn, region_id, events)
    update_last_tick_at(conn, region_id, now)

    return summary


# ---------- region lifecycle helpers (used by seeding script) ----------

def upsert_region(
    conn: psycopg.Connection,
    *,
    name: str,
    kind: str = "wilderness",
    tick_interval_seconds: int = 180,
) -> int:
    """Create a region by name if it doesn't exist; return its id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO regions (name, kind, tick_interval_seconds)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO UPDATE
                SET kind = EXCLUDED.kind,
                    tick_interval_seconds = EXCLUDED.tick_interval_seconds
            RETURNING id
            """,
            (name, kind, tick_interval_seconds),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def assign_entity_to_region(
    conn: psycopg.Connection, entity_id: int, region_id: int, *, zone_label: str
) -> None:
    """Set ``entity_zones.region_id`` (and the legacy ``zone`` text for back-compat)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_zones (entity_id, zone, region_id, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (entity_id) DO UPDATE
                SET zone = EXCLUDED.zone,
                    region_id = EXCLUDED.region_id,
                    updated_at = NOW()
            """,
            (entity_id, zone_label, region_id),
        )

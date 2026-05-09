"""Append-only world_events writer.

Systems return ``PendingEvent`` rows; the tick orchestrator collects them
and flushes here in one ``executemany`` per tick. Unreal reads from
``world_events`` (see roadmap §5.4) on region entry to summarise what
happened while the player was away.

Only this module is allowed to write ``world_events``.
"""
from __future__ import annotations

import json
from typing import Iterable

import psycopg

from .state import PendingEvent


def bulk_insert_events(
    conn: psycopg.Connection,
    region_id: int,
    events: Iterable[PendingEvent],
) -> int:
    """Insert all pending events for a region in one round-trip. Returns count."""
    rows = [
        (
            region_id,
            ev.kind,
            ev.subject_entity_id,
            ev.target_entity_id,
            json.dumps(ev.payload) if ev.payload is not None else None,
        )
        for ev in events
    ]
    if not rows:
        return 0

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO world_events (
                region_id, kind, subject_entity_id, target_entity_id, payload
            ) VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            rows,
        )
    return len(rows)

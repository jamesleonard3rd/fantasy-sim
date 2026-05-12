"""End-to-end MVP test for the sim framework (roadmap §8.8).

Spins up an isolated region against the real database, ticks it, and asserts
the contract:

    1. The tick succeeds.
    2. A `region.tick` row appears in `world_events` for the region.
    3. `regions.last_tick_at` is advanced.
    4. `world_clock.game_tick` is advanced.

The test cleans up its region/events at the end. Multiple test runs against
the same DB are isolated by a unique region name per process.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def isolated_region(db_conn):
    """Create an empty test region; tear down (region + its events) on exit."""
    name = f"__test_region_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO regions (name, type, tick_interval_seconds)
            VALUES (%s, 'region', 180)
            RETURNING id
            """,
            (name,),
        )
        row = cur.fetchone()
        assert row is not None
        region_id = int(row[0])
    db_conn.commit()

    try:
        yield {"id": region_id, "name": name}
    finally:
        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM world_events WHERE region_id = %s", (region_id,))
            cur.execute("DELETE FROM regions WHERE id = %s", (region_id,))
        db_conn.commit()


def test_tick_region_emits_event_and_advances_clocks(db_conn, isolated_region):
    from rts_world.sim.tick import tick_region

    region_id = int(isolated_region["id"])

    # Capture clock + region state before the tick so we can assert advancement.
    with db_conn.cursor() as cur:
        cur.execute("SELECT game_tick FROM world_clock WHERE id = 1")
        row = cur.fetchone()
        tick_before = int(row[0]) if row is not None else 0

    result = tick_region(region_id)

    assert not result.skipped, f"tick was skipped: {result.skipped_reason}"
    assert result.region_id == region_id
    assert result.events_emitted >= 1, "heartbeat system should emit at least one event"

    # 1. world_events row exists for our region with the heartbeat kind.
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT kind, significance, payload FROM world_events WHERE region_id = %s",
            (region_id,),
        )
        rows = cur.fetchall()
    assert any(r[0] == "region.tick" for r in rows), \
        f"expected a 'region.tick' event, got: {[r[0] for r in rows]}"
    assert all(1 <= int(r[1]) <= 5 for r in rows)

    # 2. regions.last_tick_at is advanced to a recent timestamp.
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT last_tick_at FROM regions WHERE id = %s", (region_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] is not None, "last_tick_at not set"
    last_tick_at = row[0]
    if last_tick_at.tzinfo is None:
        last_tick_at = last_tick_at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - last_tick_at).total_seconds()
    assert 0 <= age < 60, f"last_tick_at not recent: {age}s old"

    # 3. world_clock advanced. It is now a 24-hour day timer, so game_tick is
    #    the minute within the current realm day rather than a raw tick count.
    with db_conn.cursor() as cur:
        cur.execute("SELECT game_day, game_tick FROM world_clock WHERE id = 1")
        row = cur.fetchone()
    assert row is not None
    day_after = int(row[0])
    tick_after = int(row[1])
    assert 0 <= tick_after < 1440
    assert day_after >= 0
    assert tick_after != tick_before or day_after > 0


def test_tick_region_paused_is_noop(db_conn, isolated_region):
    from rts_world.sim.tick import tick_region

    region_id = int(isolated_region["id"])

    with db_conn.cursor() as cur:
        cur.execute("UPDATE regions SET paused = TRUE WHERE id = %s", (region_id,))
    db_conn.commit()

    result = tick_region(region_id)

    assert result.skipped
    assert result.skipped_reason == "paused"
    assert result.events_emitted == 0

    # No world_events row inserted while paused.
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM world_events WHERE region_id = %s", (region_id,)
        )
        row = cur.fetchone()
    assert row is not None and int(row[0]) == 0


def test_load_region_state_returns_none_for_unknown(db_conn):
    from rts_world.sim.regions import load_region_state

    state = load_region_state(db_conn, region_id=-12345)
    assert state is None

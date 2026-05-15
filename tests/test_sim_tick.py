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

import json
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
            INSERT INTO regions (key, name, type, tick_interval_seconds)
            VALUES (%s, %s, 'region', 180)
            RETURNING id
            """,
            (name, name),
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


def test_list_unpaused_regions_excludes_subregions(db_conn):
    from rts_world.sim.regions import list_unpaused_regions

    parent_name = f"__test_parent_region_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    child_name = f"__test_child_region_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    parent_id: int | None = None
    child_id: int | None = None

    try:
        with db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO regions (key, name, type, tick_interval_seconds)
                VALUES (%s, %s, 'region', 180)
                RETURNING id
                """,
                (parent_name, parent_name),
            )
            parent_row = cur.fetchone()
            assert parent_row is not None
            parent_id = int(parent_row[0])

            cur.execute(
                """
                INSERT INTO regions (key, name, type, parent_id, tick_interval_seconds)
                VALUES (%s, %s, 'border', %s, 180)
                RETURNING id
                """,
                (child_name, child_name, parent_id),
            )
            child_row = cur.fetchone()
            assert child_row is not None
            child_id = int(child_row[0])
        db_conn.commit()

        listed_ids = {int(region["id"]) for region in list_unpaused_regions(db_conn)}

        assert parent_id in listed_ids
        assert child_id not in listed_ids
    finally:
        db_conn.rollback()
        with db_conn.cursor() as cur:
            if child_id is not None:
                cur.execute("DELETE FROM world_events WHERE region_id = %s", (child_id,))
                cur.execute("DELETE FROM regions WHERE id = %s", (child_id,))
            if parent_id is not None:
                cur.execute("DELETE FROM world_events WHERE region_id = %s", (parent_id,))
                cur.execute("DELETE FROM regions WHERE id = %s", (parent_id,))
        db_conn.commit()


def test_load_region_state_includes_entities_in_subregions(db_conn, isolated_region):
    from rts_world.sim.regions import load_region_state

    parent_id = int(isolated_region["id"])
    child_name = f"__test_child_region_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    race_name = f"__test_subregion_race_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    child_id: int | None = None
    race_id: int | None = None
    entity_id: int | None = None

    try:
        with db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO regions (key, name, type, parent_id, tick_interval_seconds)
                VALUES (%s, %s, 'border', %s, 180)
                RETURNING id
                """,
                (child_name, child_name, parent_id),
            )
            child_row = cur.fetchone()
            assert child_row is not None
            child_id = int(child_row[0])

            cur.execute("INSERT INTO races (name) VALUES (%s) RETURNING id", (race_name,))
            race_row = cur.fetchone()
            assert race_row is not None
            race_id = int(race_row[0])

            cur.execute(
                """
                INSERT INTO entities (name, type, race_id)
                VALUES ('Subregion Tester', 'humanoid', %s)
                RETURNING id
                """,
                (race_id,),
            )
            entity_row = cur.fetchone()
            assert entity_row is not None
            entity_id = int(entity_row[0])

            cur.execute(
                """
                INSERT INTO entity_zones (entity_id, zone, region_id)
                VALUES (%s, %s, %s)
                """,
                (entity_id, child_name, child_id),
            )
        db_conn.commit()

        state = load_region_state(db_conn, parent_id)

        assert state is not None
        assert entity_id in state.entities_by_id
        assert state.entities_by_id[entity_id]["region_id"] == child_id
    finally:
        db_conn.rollback()
        with db_conn.cursor() as cur:
            if entity_id is not None:
                cur.execute("DELETE FROM entities WHERE id = %s", (entity_id,))
            if child_id is not None:
                cur.execute("DELETE FROM world_events WHERE region_id = %s", (child_id,))
                cur.execute("DELETE FROM regions WHERE id = %s", (child_id,))
            if race_id is not None:
                cur.execute("DELETE FROM races WHERE id = %s", (race_id,))
        db_conn.commit()


def test_tick_region_executes_persisted_travel_goal(db_conn, isolated_region):
    from rts_world.sim.tick import tick_region

    source_region_id = int(isolated_region["id"])
    target_name = f"__test_target_region_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    race_name = f"__test_race_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    entity_id: int | None = None
    target_region_id: int | None = None
    race_id: int | None = None

    try:
        with db_conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.entity_goals')")
            table_row = cur.fetchone()
            if table_row is None or table_row[0] is None:
                pytest.skip("entity_goals table is not present; apply schema.sql")

            cur.execute("INSERT INTO races (name) VALUES (%s) RETURNING id", (race_name,))
            race_row = cur.fetchone()
            assert race_row is not None
            race_id = int(race_row[0])

            cur.execute(
                """
                INSERT INTO regions (key, name, type, tick_interval_seconds)
                VALUES (%s, %s, 'region', 180)
                RETURNING id
                """,
                (target_name, target_name),
            )
            target_row = cur.fetchone()
            assert target_row is not None
            target_region_id = int(target_row[0])

            cur.execute(
                """
                INSERT INTO entities (name, type, race_id)
                VALUES ('Goal Tester', 'humanoid', %s)
                RETURNING id
                """,
                (race_id,),
            )
            entity_row = cur.fetchone()
            assert entity_row is not None
            entity_id = int(entity_row[0])

            cur.execute(
                """
                INSERT INTO entity_zones (entity_id, zone, region_id)
                VALUES (%s, %s, %s)
                """,
                (entity_id, isolated_region["name"], source_region_id),
            )
            cur.execute(
                """
                INSERT INTO entity_goals (
                    entity_id, goal_type, priority, urgency, payload
                ) VALUES (
                    %s, 'travel_to_region', 4, 0, %s::jsonb
                )
                RETURNING id
                """,
                (entity_id, f'{{"region_id": {target_region_id}, "duration_ticks": 1}}'),
            )
            goal_row = cur.fetchone()
            assert goal_row is not None
            goal_id = int(goal_row[0])
        db_conn.commit()

        result = tick_region(source_region_id)

        assert not result.skipped
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, active, progress, completed_at_game_tick
                  FROM entity_goals
                 WHERE id = %s
                """,
                (goal_id,),
            )
            goal_state = cur.fetchone()
            assert goal_state is not None
            assert goal_state[0] == "completed"
            assert goal_state[1] is False
            assert int(goal_state[2]) == 100
            assert goal_state[3] is not None

            cur.execute(
                "SELECT region_id FROM entity_zones WHERE entity_id = %s",
                (entity_id,),
            )
            zone_row = cur.fetchone()
            assert zone_row is not None
            assert int(zone_row[0]) == target_region_id

            cur.execute(
                """
                SELECT kind
                  FROM world_events
                 WHERE region_id = %s AND subject_entity_id = %s
                 ORDER BY id
                """,
                (source_region_id, entity_id),
            )
            kinds = [row[0] for row in cur.fetchall()]
            assert "goal.activated" in kinds
            assert "goal.completed" in kinds
    finally:
        db_conn.rollback()
        with db_conn.cursor() as cur:
            if entity_id is not None:
                cur.execute("DELETE FROM world_events WHERE subject_entity_id = %s", (entity_id,))
                cur.execute("DELETE FROM entities WHERE id = %s", (entity_id,))
            if target_region_id is not None:
                cur.execute("DELETE FROM world_events WHERE region_id = %s", (target_region_id,))
                cur.execute("DELETE FROM regions WHERE id = %s", (target_region_id,))
            if race_id is not None:
                cur.execute("DELETE FROM races WHERE id = %s", (race_id,))
        db_conn.commit()


def test_tick_region_executes_persisted_tournament(db_conn, isolated_region):
    from rts_world.sim.tick import tick_region

    region_id = int(isolated_region["id"])
    race_name = f"__test_tournament_race_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    race_id: int | None = None
    entity_ids: list[int] = []
    tournament_id: int | None = None

    try:
        with db_conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.tournament_instances')")
            table_row = cur.fetchone()
            if table_row is None or table_row[0] is None:
                pytest.skip("tournament tables are not present; apply schema.sql")

            cur.execute("INSERT INTO races (name) VALUES (%s) RETURNING id", (race_name,))
            race_row = cur.fetchone()
            assert race_row is not None
            race_id = int(race_row[0])

            for index in range(4):
                cur.execute(
                    """
                    INSERT INTO entities (name, type, race_id)
                    VALUES (%s, 'humanoid', %s)
                    RETURNING id
                    """,
                    (f"Tournament Tester {index}", race_id),
                )
                entity_row = cur.fetchone()
                assert entity_row is not None
                entity_id = int(entity_row[0])
                entity_ids.append(entity_id)
                cur.execute(
                    """
                    INSERT INTO entity_zones (entity_id, zone, region_id)
                    VALUES (%s, %s, %s)
                    """,
                    (entity_id, isolated_region["name"], region_id),
                )

            cur.execute(
                """
                INSERT INTO tournament_instances (
                    region_id, name, status, starts_at_game_tick,
                    current_round, max_rounds_per_tick, payload
                ) VALUES (
                    %s, 'Integration Cup', 'registration_closed', 0,
                    0, 10, %s::jsonb
                )
                RETURNING id
                """,
                (region_id, json.dumps({"min_participants": 2})),
            )
            tournament_row = cur.fetchone()
            assert tournament_row is not None
            tournament_id = int(tournament_row[0])

            for seed, entity_id in enumerate(entity_ids, start=1):
                cur.execute(
                    """
                    INSERT INTO tournament_participants (
                        tournament_id, entity_id, status, seed, joined_at_game_tick
                    ) VALUES (%s, %s, 'registered', %s, 0)
                    """,
                    (tournament_id, entity_id, seed),
                )
        db_conn.commit()

        result = tick_region(region_id)

        assert not result.skipped
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, winner_entity_id, current_round, completed_at_game_tick
                  FROM tournament_instances
                 WHERE id = %s
                """,
                (tournament_id,),
            )
            tournament_row = cur.fetchone()
            assert tournament_row is not None
            assert tournament_row[0] == "completed"
            assert int(tournament_row[1]) == entity_ids[0]
            assert int(tournament_row[2]) == 2
            assert tournament_row[3] is not None

            cur.execute(
                """
                SELECT status, COUNT(*)
                  FROM tournament_participants
                 WHERE tournament_id = %s
                 GROUP BY status
                """,
                (tournament_id,),
            )
            statuses = {row[0]: int(row[1]) for row in cur.fetchall()}
            assert statuses == {"winner": 1, "eliminated": 3}

            cur.execute(
                """
                SELECT kind
                  FROM world_events
                 WHERE region_id = %s
                 ORDER BY id
                """,
                (region_id,),
            )
            kinds = [row[0] for row in cur.fetchall()]
            assert "tournament.started" in kinds
            assert "tournament.winner_declared" in kinds
    finally:
        db_conn.rollback()
        with db_conn.cursor() as cur:
            if tournament_id is not None:
                cur.execute(
                    "DELETE FROM tournament_instances WHERE id = %s",
                    (tournament_id,),
                )
            if entity_ids:
                cur.execute("DELETE FROM entities WHERE id = ANY(%s)", (entity_ids,))
            if race_id is not None:
                cur.execute("DELETE FROM races WHERE id = %s", (race_id,))
        db_conn.commit()

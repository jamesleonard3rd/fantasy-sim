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

import json
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
            SELECT id, key, name, type, parent_id, tick_interval_seconds,
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
            "key": row[1],
            "name": row[2],
            "type": row[3],
            "parent_id": int(row[4]) if row[4] is not None else None,
            "tick_interval_seconds": int(row[5]),
            "last_tick_at": row[6],
            "paused": bool(row[7]),
        }


def query_due_regions(
    conn: psycopg.Connection, *, now: datetime
) -> list[dict[str, Any]]:
    """Root regions that are unpaused AND whose next tick is due at or before ``now``.

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
               AND parent_id IS NULL
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
    """Unpaused root regions, with the fields the scheduler needs to schedule them."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, tick_interval_seconds, last_tick_at
              FROM regions
             WHERE paused = FALSE
               AND parent_id IS NULL
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


def _sim_region_ids(conn: psycopg.Connection, region_id: int) -> list[int]:
    """Return a root region plus all unpaused descendants that tick with it."""
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH RECURSIVE sim_regions AS (
                SELECT id
                  FROM regions
                 WHERE id = %s
                UNION ALL
                SELECT child.id
                  FROM regions child
                  JOIN sim_regions parent ON child.parent_id = parent.id
                 WHERE child.paused = FALSE
            )
            SELECT id FROM sim_regions
            """,
            (region_id,),
        )
        return [int(row[0]) for row in cur.fetchall()]


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
    sim_region_ids = _sim_region_ids(conn, region_id)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, key, name, type, parent_id
              FROM regions
             ORDER BY id
            """
        )
        for row in cur.fetchall():
            state.regions_by_id[int(row[0])] = {
                "id": int(row[0]),
                "key": row[1],
                "name": row[2],
                "type": row[3],
                "parent_id": int(row[4]) if row[4] is not None else None,
            }

        # Region control: which factions own/control regions in this sim scope.
        cur.execute(
            """
            SELECT region_id, role, faction_id, since_game_tick, updated_at
              FROM region_control
             WHERE region_id = ANY(%s)
             ORDER BY region_id, role
            """,
            (sim_region_ids,),
        )
        for row in cur.fetchall():
            state.add_region_control(
                {
                    "region_id": int(row[0]),
                    "role": row[1],
                    "faction_id": int(row[2]),
                    "since_game_tick": int(row[3]) if row[3] is not None else None,
                    "updated_at": row[4],
                }
            )

        faction_ids = sorted({int(r["faction_id"]) for r in state.region_control})
        if faction_ids:
            cur.execute(
                """
                SELECT id, name, kind, parent_id
                  FROM factions
                 WHERE id = ANY(%s)
                 ORDER BY name
                """,
                (faction_ids,),
            )
            for row in cur.fetchall():
                state.add_faction(
                    {
                        "id": int(row[0]),
                        "name": row[1],
                        "kind": row[2],
                        "parent_id": int(row[3]) if row[3] is not None else None,
                    }
                )

        cur.execute("SELECT to_regclass('public.tournament_instances')")
        tournament_table = cur.fetchone()
        if tournament_table is not None and tournament_table[0] is not None:
            cur.execute(
                """
                SELECT id, region_id, name, status,
                       registration_opens_at_game_tick,
                       registration_closes_at_game_tick,
                       starts_at_game_tick, current_round, max_rounds_per_tick,
                       winner_entity_id, payload, created_at, updated_at,
                       completed_at_game_tick
                  FROM tournament_instances
                 WHERE region_id = ANY(%s)
                   AND status NOT IN ('completed', 'cancelled')
                 ORDER BY starts_at_game_tick, id
                """,
                (sim_region_ids,),
            )
            for row in cur.fetchall():
                tournament = {
                    "id": int(row[0]),
                    "region_id": int(row[1]),
                    "name": row[2],
                    "status": row[3],
                    "registration_opens_at_game_tick": (
                        int(row[4]) if row[4] is not None else None
                    ),
                    "registration_closes_at_game_tick": (
                        int(row[5]) if row[5] is not None else None
                    ),
                    "starts_at_game_tick": int(row[6]),
                    "current_round": int(row[7]),
                    "max_rounds_per_tick": int(row[8]),
                    "winner_entity_id": int(row[9]) if row[9] is not None else None,
                    "payload": row[10] or {},
                    "created_at": row[11],
                    "updated_at": row[12],
                    "completed_at_game_tick": int(row[13]) if row[13] is not None else None,
                }
                state.add_tournament(tournament)

            if state.tournaments_by_id:
                tournament_ids = tuple(state.tournaments_by_id.keys())
                cur.execute(
                    """
                    SELECT tournament_id, entity_id, status, seed,
                           eliminated_round, joined_at_game_tick, payload,
                           updated_at
                      FROM tournament_participants
                     WHERE tournament_id = ANY(%s)
                     ORDER BY tournament_id, seed NULLS LAST, entity_id
                    """,
                    (list(tournament_ids),),
                )
                for row in cur.fetchall():
                    participant = {
                        "tournament_id": int(row[0]),
                        "entity_id": int(row[1]),
                        "status": row[2],
                        "seed": int(row[3]) if row[3] is not None else None,
                        "eliminated_round": int(row[4]) if row[4] is not None else None,
                        "joined_at_game_tick": int(row[5]) if row[5] is not None else None,
                        "payload": row[6] or {},
                        "updated_at": row[7],
                    }
                    state.add_tournament_participant(participant)

        # Entities currently zoned to this region or any unpaused subregion.
        # The wide SELECT pattern: one round-trip, no per-entity follow-ups.
        cur.execute(
            """
            SELECT e.id, e.name, e.type, e.race_id, e.subrace_id, e.created_at,
                   z.zone, z.region_id
              FROM entities e
              JOIN entity_zones z ON z.entity_id = e.id
             WHERE z.region_id = ANY(%s)
             ORDER BY e.id
            """,
            (sim_region_ids,),
        )
        for row in cur.fetchall():
            ent: dict[str, object] = {
                "id": int(row[0]),
                "name": row[1],
                "type": row[2],
                "race_id": int(row[3]),
                "subrace_id": int(row[4]) if row[4] is not None else None,
                "created_at": row[5],
                "zone": row[6],
                "region_id": int(row[7]) if row[7] is not None else None,
            }
            state.entities.append(ent)
            state.entities_by_id[int(row[0])] = ent

        if state.entities_by_id:
            ids = tuple(state.entities_by_id.keys())

            # Unified membership rank signal for factions relevant to this region scope.
            if state.factions_by_id:
                faction_ids = list(state.factions_by_id.keys())

                cur.execute(
                    """
                    SELECT ef.entity_id, ef.faction_id, ef.rank, f.kind
                      FROM entity_factions ef
                      JOIN factions f ON f.id = ef.faction_id
                     WHERE ef.entity_id  = ANY(%s)
                       AND ef.faction_id = ANY(%s)
                    """,
                    (list(ids), faction_ids),
                )
                for row in cur.fetchall():
                    state.add_member(
                        {
                            "entity_id": int(row[0]),
                            "faction_id": int(row[1]),
                            "rank": row[2],
                            "source": "house" if row[3] == "house" else "faction",
                        }
                    )

                cur.execute(
                    """
                    SELECT id, faction_id, entity_id, region_id, order_type, status,
                           payload, created_at_game_tick, completed_at_game_tick,
                           created_at, updated_at
                      FROM faction_orders
                     WHERE faction_id = ANY(%s)
                       AND status = 'active'
                     ORDER BY id
                    """,
                    (faction_ids,),
                )
                for row in cur.fetchall():
                    state.add_faction_order(
                        {
                            "id": int(row[0]),
                            "faction_id": int(row[1]),
                            "entity_id": int(row[2]) if row[2] is not None else None,
                            "region_id": int(row[3]) if row[3] is not None else None,
                            "order_type": row[4],
                            "status": row[5],
                            "payload": row[6] or {},
                            "created_at_game_tick": (
                                int(row[7]) if row[7] is not None else None
                            ),
                            "completed_at_game_tick": (
                                int(row[8]) if row[8] is not None else None
                            ),
                            "created_at": row[9],
                            "updated_at": row[10],
                        }
                    )
            cur.execute(
                """
                SELECT id, entity_id, parent_goal_id, goal_type, status,
                       priority, urgency, deadline_game_tick, interruptible,
                       completion_mode, active, progress, cost, danger,
                       payload, created_at, updated_at, started_at_game_tick,
                       paused_at_game_tick, completed_at_game_tick
                  FROM entity_goals
                 WHERE entity_id = ANY(%s)
                 ORDER BY entity_id, parent_goal_id NULLS FIRST, id
                """,
                (list(ids),),
            )
            for row in cur.fetchall():
                goal = {
                    "id": int(row[0]),
                    "entity_id": int(row[1]),
                    "parent_goal_id": int(row[2]) if row[2] is not None else None,
                    "goal_type": row[3],
                    "status": row[4],
                    "priority": int(row[5]),
                    "urgency": int(row[6]),
                    "deadline_game_tick": int(row[7]) if row[7] is not None else None,
                    "interruptible": bool(row[8]),
                    "completion_mode": row[9],
                    "active": bool(row[10]),
                    "progress": float(row[11]),
                    "cost": float(row[12]),
                    "danger": float(row[13]),
                    "payload": row[14] or {},
                    "created_at": row[15],
                    "updated_at": row[16],
                    "started_at_game_tick": int(row[17]) if row[17] is not None else None,
                    "paused_at_game_tick": int(row[18]) if row[18] is not None else None,
                    "completed_at_game_tick": int(row[19]) if row[19] is not None else None,
                }
                state.add_goal(goal)

            # Relationships among entities currently in this region. We deliberately
            # only load rows where BOTH endpoints are in-region; cross-region
            # relationships are a separate concern (faction politics handles that).
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

            cur.execute(
                """
                SELECT id, subject_entity_id, target_entity_id, source_type,
                       source_key, source_instance, value, decay_per_tick,
                       expires_at_game_tick, payload, updated_at
                  FROM relationship_terms
                 WHERE subject_entity_id = ANY(%s)
                   AND target_entity_id  = ANY(%s)
                 ORDER BY id
                """,
                (list(ids), list(ids)),
            )
            for row in cur.fetchall():
                state.relationship_terms.append(
                    {
                        "id": int(row[0]),
                        "subject_entity_id": int(row[1]),
                        "target_entity_id": int(row[2]),
                        "source_type": row[3],
                        "source_key": row[4],
                        "source_instance": row[5],
                        "value": int(row[6]),
                        "decay_per_tick": int(row[7]),
                        "expires_at_game_tick": int(row[8]) if row[8] is not None else None,
                        "payload": row[9],
                        "updated_at": row[10],
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
        "goals_inserted": 0,
        "goals_updated": 0,
        "tournaments_updated": 0,
        "tournament_participants_updated": 0,
        "relationships_updated": 0,
        "relationship_terms_updated": 0,
        "events_inserted": 0,
    }

    region_id = state.region_id

    # Relationship terms: bulk update changed contribution rows. New terms are
    # inserted by the system that creates them; this path owns per-tick mutation
    # such as decay toward zero.
    if state.dirty_relationship_term_ids:
        by_id = {int(t["id"]): t for t in state.relationship_terms if t.get("id") is not None}
        rows = []
        for term_id in state.dirty_relationship_term_ids:
            term = by_id.get(term_id)
            if term is None:
                continue
            rows.append(
                (
                    int(term["value"]),
                    int(term.get("decay_per_tick", 0)),
                    term.get("expires_at_game_tick"),
                    json.dumps(term.get("payload")) if term.get("payload") is not None else None,
                    term_id,
                )
            )
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    UPDATE relationship_terms
                       SET value = %s,
                           decay_per_tick = %s,
                           expires_at_game_tick = %s,
                           payload = %s::jsonb,
                           updated_at = NOW()
                     WHERE id = %s
                    """,
                    rows,
                )
            summary["relationship_terms_updated"] = len(rows)

    # Relationships: upsert only the dirty cached opinions.
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
                    INSERT INTO relationships (
                        opinion, subject_entity_id, target_entity_id, last_updated
                    )
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (subject_entity_id, target_entity_id) DO UPDATE
                        SET opinion = EXCLUDED.opinion,
                            last_updated = NOW()
                    """,
                    rows,
                )
            summary["relationships_updated"] = len(rows)

    # Goals: flush dirty existing rows before inserting new rows so an old active
    # goal can be paused before a newly-created child becomes active.
    if state.dirty_goal_ids:
        by_id = {
            int(goal["id"]): goal
            for goal in state.goals
            if goal.get("id") is not None
        }
        rows = []
        for goal_id in state.dirty_goal_ids:
            goal = by_id.get(goal_id)
            if goal is None:
                continue
            rows.append(
                (
                    goal.get("parent_goal_id"),
                    goal["goal_type"],
                    goal.get("status", "pending"),
                    int(goal.get("priority", 3)),
                    int(goal.get("urgency", 0)),
                    goal.get("deadline_game_tick"),
                    bool(goal.get("interruptible", True)),
                    goal.get("completion_mode", "ordered"),
                    bool(goal.get("active", False)),
                    float(goal.get("progress", 0)),
                    float(goal.get("cost", 0)),
                    float(goal.get("danger", 0)),
                    json.dumps(goal.get("payload") or {}),
                    goal.get("started_at_game_tick"),
                    goal.get("paused_at_game_tick"),
                    goal.get("completed_at_game_tick"),
                    goal_id,
                )
            )
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    UPDATE entity_goals
                       SET parent_goal_id = %s,
                           goal_type = %s,
                           status = %s,
                           priority = %s,
                           urgency = %s,
                           deadline_game_tick = %s,
                           interruptible = %s,
                           completion_mode = %s,
                           active = %s,
                           progress = %s,
                           cost = %s,
                           danger = %s,
                           payload = %s::jsonb,
                           started_at_game_tick = %s,
                           paused_at_game_tick = %s,
                           completed_at_game_tick = %s,
                           updated_at = NOW()
                     WHERE id = %s
                    """,
                    rows,
                )
            summary["goals_updated"] = len(rows)

    new_goal_rows = [
        (
            int(goal["entity_id"]),
            goal.get("parent_goal_id"),
            goal["goal_type"],
            goal.get("status", "pending"),
            int(goal.get("priority", 3)),
            int(goal.get("urgency", 0)),
            goal.get("deadline_game_tick"),
            bool(goal.get("interruptible", True)),
            goal.get("completion_mode", "ordered"),
            bool(goal.get("active", False)),
            float(goal.get("progress", 0)),
            float(goal.get("cost", 0)),
            float(goal.get("danger", 0)),
            json.dumps(goal.get("payload") or {}),
            goal.get("started_at_game_tick"),
            goal.get("paused_at_game_tick"),
            goal.get("completed_at_game_tick"),
        )
        for goal in state.goals
        if goal.get("id") is None
    ]
    if new_goal_rows:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO entity_goals (
                    entity_id, parent_goal_id, goal_type, status, priority,
                    urgency, deadline_game_tick, interruptible, completion_mode,
                    active, progress, cost, danger, payload,
                    started_at_game_tick, paused_at_game_tick, completed_at_game_tick
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s::jsonb,
                    %s, %s, %s
                )
                """,
                new_goal_rows,
            )
        summary["goals_inserted"] = len(new_goal_rows)

    # Faction orders: update dirty existing rows, then insert new rows.
    if state.dirty_faction_order_ids:
        by_id = {
            int(order["id"]): order
            for order in state.faction_orders
            if order.get("id") is not None
        }
        rows = []
        for oid in state.dirty_faction_order_ids:
            order = by_id.get(oid)
            if order is None:
                continue
            rows.append(
                (
                    order.get("entity_id"),
                    order.get("region_id"),
                    order.get("order_type"),
                    order.get("status", "active"),
                    json.dumps(order.get("payload") or {}),
                    order.get("created_at_game_tick"),
                    order.get("completed_at_game_tick"),
                    oid,
                )
            )
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    UPDATE faction_orders
                       SET entity_id = %s,
                           region_id = %s,
                           order_type = %s,
                           status = %s,
                           payload = %s::jsonb,
                           created_at_game_tick = %s,
                           completed_at_game_tick = %s,
                           updated_at = NOW()
                     WHERE id = %s
                    """,
                    rows,
                )
            summary["faction_orders_updated"] = len(rows)

    new_order_rows = [
        (
            int(order["faction_id"]),
            order.get("entity_id"),
            order.get("region_id"),
            order["order_type"],
            order.get("status", "active"),
            json.dumps(order.get("payload") or {}),
            order.get("created_at_game_tick"),
            order.get("completed_at_game_tick"),
        )
        for order in state.faction_orders
        if order.get("id") is None
    ]
    if new_order_rows:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO faction_orders (
                    faction_id, entity_id, region_id, order_type, status, payload,
                    created_at_game_tick, completed_at_game_tick,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s::jsonb,
                    %s, %s,
                    NOW(), NOW()
                )
                """,
                new_order_rows,
            )
        summary["faction_orders_inserted"] = len(new_order_rows)

    # Entities: mutable simulation state currently lives in component tables.
    # Goal execution uses this path to move an entity between regions.
    if state.dirty_entity_ids:
        rows = []
        for entity_id in state.dirty_entity_ids:
            entity = state.entities_by_id.get(entity_id)
            if entity is None:
                continue
            region_id_value = entity.get("region_id")
            zone = entity.get("zone") or str(state.region["name"])
            rows.append(
                (
                    int(entity_id),
                    str(zone),
                    int(region_id_value) if region_id_value is not None else None,
                )
            )
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO entity_zones (entity_id, zone, region_id, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (entity_id) DO UPDATE
                        SET zone = EXCLUDED.zone,
                            region_id = EXCLUDED.region_id,
                            updated_at = NOW()
                    """,
                    rows,
                )
            summary["entities_updated"] = len(rows)

    if state.dirty_tournament_ids:
        by_id = {int(t["id"]): t for t in state.tournaments}
        rows = []
        for tournament_id in state.dirty_tournament_ids:
            tournament = by_id.get(tournament_id)
            if tournament is None:
                continue
            rows.append(
                (
                    tournament["name"],
                    tournament.get("status", "scheduled"),
                    tournament.get("registration_opens_at_game_tick"),
                    tournament.get("registration_closes_at_game_tick"),
                    tournament["starts_at_game_tick"],
                    int(tournament.get("current_round", 0)),
                    int(tournament.get("max_rounds_per_tick", 1)),
                    tournament.get("winner_entity_id"),
                    json.dumps(tournament.get("payload") or {}),
                    tournament.get("completed_at_game_tick"),
                    tournament_id,
                )
            )
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    UPDATE tournament_instances
                       SET name = %s,
                           status = %s,
                           registration_opens_at_game_tick = %s,
                           registration_closes_at_game_tick = %s,
                           starts_at_game_tick = %s,
                           current_round = %s,
                           max_rounds_per_tick = %s,
                           winner_entity_id = %s,
                           payload = %s::jsonb,
                           completed_at_game_tick = %s,
                           updated_at = NOW()
                     WHERE id = %s
                    """,
                    rows,
                )
            summary["tournaments_updated"] = len(rows)

    if state.dirty_tournament_participant_keys:
        by_key = {
            (int(p["tournament_id"]), int(p["entity_id"])): p
            for p in state.tournament_participants
        }
        rows = []
        for key in state.dirty_tournament_participant_keys:
            participant = by_key.get(key)
            if participant is None:
                continue
            rows.append(
                (
                    key[0],
                    key[1],
                    participant.get("status", "registered"),
                    participant.get("seed"),
                    participant.get("eliminated_round"),
                    participant.get("joined_at_game_tick"),
                    json.dumps(participant.get("payload") or {}),
                )
            )
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO tournament_participants (
                        tournament_id, entity_id, status, seed,
                        eliminated_round, joined_at_game_tick, payload,
                        updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (tournament_id, entity_id) DO UPDATE
                        SET status = EXCLUDED.status,
                            seed = EXCLUDED.seed,
                            eliminated_round = EXCLUDED.eliminated_round,
                            joined_at_game_tick = EXCLUDED.joined_at_game_tick,
                            payload = EXCLUDED.payload,
                            updated_at = NOW()
                    """,
                    rows,
                )
            summary["tournament_participants_updated"] = len(rows)

    summary["events_inserted"] = bulk_insert_events(conn, region_id, events)
    update_last_tick_at(conn, region_id, now)

    return summary


# ---------- region lifecycle helpers (used by seeding script) ----------

def upsert_region(
    conn: psycopg.Connection,
    *,
    key: str,
    name: str,
    region_type: str = "region",
    parent_id: int | None = None,
    tick_interval_seconds: int = 180,
    paused: bool = False,
) -> int:
    """Create a region by stable key if it doesn't exist; return its id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO regions (key, name, type, parent_id, tick_interval_seconds, paused)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (key) DO UPDATE
                SET name = EXCLUDED.name,
                    type = EXCLUDED.type,
                    parent_id = EXCLUDED.parent_id,
                    tick_interval_seconds = EXCLUDED.tick_interval_seconds,
                    paused = EXCLUDED.paused
            RETURNING id
            """,
            (key, name, region_type, parent_id, tick_interval_seconds, paused),
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


def set_region_control(
    conn: psycopg.Connection,
    region_id: int,
    faction_id: int,
    *,
    role: str,
    since_game_tick: int | None = None,
) -> None:
    """Assign owner/controller for a region."""
    if role not in {"owner", "controller"}:
        raise ValueError(f"unsupported region control role: {role}")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO region_control (
                region_id, role, faction_id, since_game_tick, updated_at
            )
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (region_id, role) DO UPDATE
                SET faction_id = EXCLUDED.faction_id,
                    since_game_tick = EXCLUDED.since_game_tick,
                    updated_at = NOW()
            """,
            (
                region_id,
                role,
                faction_id,
                since_game_tick,
            ),
        )

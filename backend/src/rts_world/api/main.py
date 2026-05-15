from typing import Any
from datetime import datetime, timezone

from dataclasses import asdict

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..config import commit_game_settings, get_game_settings, merge_game_settings_in_memory
from ..db.db import get_connection
from ..services import entities as entity_service
from ..sim.control import sim_controller, sim_status_dict
from ..sim.travel import route_travel_segments
from ..sim.clock import (
    GAME_MINUTES_PER_DAY,
    game_minutes_per_real_second,
    real_seconds_per_game_day,
)

app = FastAPI(title="Fantasy Sim — Game State API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _rows_to_dicts(cur) -> list[dict]:
    cols = [c.name for c in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _entity_or_404(conn, entity_id: int) -> dict:
    entity = entity_service.get_entity_detail(conn, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


def _raise_entity_service_error(exc: entity_service.EntityServiceError) -> None:
    raise HTTPException(
        status_code=getattr(exc, "status_code", 400),
        detail=exc.detail,
    ) from exc


class RealmTimeUpdate(BaseModel):
    game_day: int = Field(ge=0)
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)


_DAY_LENGTH_MULTIPLIER_MAX = 1000.0


def _validate_game_settings_patch(patch: dict[str, Any], merged: dict[str, Any]) -> None:
    sim_patch = patch.get("simulation")
    if "simulation" in patch and not isinstance(sim_patch, dict):
        raise HTTPException(status_code=400, detail="simulation must be an object")
    sim = merged.get("simulation")
    if sim is not None and not isinstance(sim, dict):
        raise HTTPException(status_code=400, detail="simulation must be an object")
    if isinstance(sim_patch, dict) and "day_length_multiplier" in sim_patch:
        raw = (sim or {}).get("day_length_multiplier")
        try:
            val = float(raw)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="simulation.day_length_multiplier must be a number",
            ) from None
        if val <= 0 or val > _DAY_LENGTH_MULTIPLIER_MAX:
            raise HTTPException(
                status_code=400,
                detail=(
                    "simulation.day_length_multiplier must be in "
                    f"(0, {_DAY_LENGTH_MULTIPLIER_MAX:g}]"
                ),
            ) from None


class EntityZoneUpdate(BaseModel):
    region_id: int
    zone: str | None = None


class EntityFactionUpdate(BaseModel):
    rank: str = Field(default="member")
    reputation: int = Field(default=0, ge=-100, le=100)


class EntityItemUpdate(BaseModel):
    quantity: int = Field(default=1, ge=0)


class EntityAbilityUpdate(BaseModel):
    level: int = Field(default=1, ge=1)


class EntityGoalCreate(BaseModel):
    goal_type: str = Field(min_length=1)
    payload: dict[str, Any] | None = None
    priority: int = Field(default=3, ge=1, le=5)
    urgency: int = Field(default=0, ge=0, le=100)
    completion_mode: str = Field(default="ordered")
    parent_goal_id: int | None = None
    interruptible: bool = True
    deadline_game_tick: int | None = None


_WORLD_EVENTS_SELECT = """
SELECT we.id, we.kind, we.significance, we.payload, we.occurred_at,
       r.name AS region_name,
       se.name AS subject_name,
       te.name AS target_name
  FROM world_events we
  LEFT JOIN regions r ON r.id = we.region_id
  LEFT JOIN entities se ON se.id = we.subject_entity_id
  LEFT JOIN entities te ON te.id = we.target_entity_id
"""

_WORLD_EVENTS_ORDER_LIMIT = """
 ORDER BY we.occurred_at DESC, we.id DESC
 LIMIT %s
"""


@app.get("/")
def root():
    return {"name": "Fantasy Sim Game State API", "status": "ok"}


# -------- Simulation control --------

@app.get("/sim/status")
def sim_status():
    return sim_status_dict(sim_controller.status())


@app.get("/sim/clock")
def sim_clock():
    running = sim_controller.status().running
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT game_day, game_tick, updated_at FROM world_clock WHERE id = 1"
            )
            row = cur.fetchone()

    if row is None:
        game_day = 0
        minute_of_day = 0
    else:
        game_day = int(row[0])
        minute_of_day = int(row[1])
        updated_at = row[2]
        if running and updated_at is not None:
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            elapsed_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
            rate = game_minutes_per_real_second()
            total_minutes = (
                game_day * GAME_MINUTES_PER_DAY
                + minute_of_day
                + max(0, round(elapsed_seconds * rate))
            )
            game_day = total_minutes // GAME_MINUTES_PER_DAY
            minute_of_day = total_minutes % GAME_MINUTES_PER_DAY

    return {
        "running": running,
        "game_day": game_day,
        "hour": minute_of_day // 60,
        "minute": minute_of_day % 60,
        "minute_of_day": minute_of_day,
        "real_seconds_per_game_day": real_seconds_per_game_day(),
    }


@app.post("/sim/start")
def sim_start():
    return sim_status_dict(sim_controller.start())


@app.post("/sim/stop")
def sim_stop():
    return sim_status_dict(sim_controller.stop())


@app.post("/settings/realm-time")
def update_realm_time(request: RealmTimeUpdate):
    minute_of_day = request.hour * 60 + request.minute
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO world_clock (id, game_day, game_tick, updated_at)
                VALUES (1, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE
                    SET game_day = EXCLUDED.game_day,
                        game_tick = EXCLUDED.game_tick,
                        updated_at = NOW()
                """,
                (request.game_day, minute_of_day),
            )
        conn.commit()
    return sim_clock()


@app.get("/settings/game-settings")
def read_game_settings():
    return get_game_settings(force_reload=True)


@app.patch("/settings/game-settings")
def patch_game_settings(payload: dict[str, Any] = Body(...)):
    if not payload:
        raise HTTPException(status_code=400, detail="Patch body must not be empty")
    try:
        merged = merge_game_settings_in_memory(payload)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    _validate_game_settings_patch(payload, merged)
    commit_game_settings(merged)
    return {
        "settings": merged,
        "real_seconds_per_game_day": real_seconds_per_game_day(),
    }


@app.get("/sim/events")
def sim_events(limit: int = 10, kind: str | None = None):
    safe_limit = max(1, min(int(limit), 50))
    kind_filter = kind.strip() if kind else None
    with get_connection() as conn:
        with conn.cursor() as cur:
            if kind_filter:
                cur.execute(
                    _WORLD_EVENTS_SELECT
                    + " WHERE we.kind = %s"
                    + _WORLD_EVENTS_ORDER_LIMIT,
                    (kind_filter, safe_limit),
                )
            else:
                cur.execute(
                    _WORLD_EVENTS_SELECT + _WORLD_EVENTS_ORDER_LIMIT,
                    (safe_limit,),
                )
            rows = _rows_to_dicts(cur)

    return [
        {
            **row,
            "message": _event_message(row),
        }
        for row in rows
    ]


def _event_message(row: dict[str, Any]) -> str:
    kind = str(row.get("kind") or "event")
    payload = row.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    if kind == "region.tick":
        region_name = payload.get("region_name") or row.get("region_name") or "A region"
        entity_count = payload.get("entity_count", 0)
        game_day = payload.get("game_day", 0)
        game_tick = payload.get("game_tick", 0)
        hour = int(game_tick) // 60
        minute = int(game_tick) % 60
        return (
            f"{region_name} advanced: {entity_count} entities simulated "
            f"(day {game_day}, {hour:02d}:{minute:02d})."
        )

    if kind == "realm.tiding":
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message

    subject = row.get("subject_name")
    target = row.get("target_name")
    if subject and target:
        return f"{subject} affected {target} ({kind})."
    if subject:
        return f"{subject} triggered {kind}."
    return kind.replace(".", " ").capitalize()


# -------- Summary (dashboard counts) --------

@app.get("/summary")
def summary():
    queries = {
        "entities": "SELECT COUNT(*) FROM entities",
        "factions": "SELECT COUNT(*) FROM factions",
        "schools": "SELECT COUNT(*) FROM schools",
        "items": "SELECT COUNT(*) FROM items",
        "abilities": "SELECT COUNT(*) FROM abilities",
        "traits": "SELECT COUNT(*) FROM traits",
        "races": "SELECT COUNT(*) FROM races",
        "subraces": "SELECT COUNT(*) FROM subraces",
        "relationships": "SELECT COUNT(*) FROM relationships",
        "houses": "SELECT COUNT(*) FROM houses",
    }
    out: dict[str, int] = {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            for key, sql in queries.items():
                cur.execute(sql)
                row = cur.fetchone()
                out[key] = int(row[0]) if row else 0
    return out


# -------- Entities --------


@app.get("/goal-templates")
def list_goal_templates():
    from ..sim.goal_templates import goal_templates

    out: list[dict[str, Any]] = []
    for goal_type, tmpl in goal_templates().items():
        req = tmpl.get("requires", [])
        if isinstance(req, str):
            requires_list = [req]
        elif isinstance(req, list):
            requires_list = [str(x) for x in req]
        else:
            requires_list = []
        out.append(
            {
                "goal_type": goal_type,
                "completion_mode": str(tmpl.get("completion_mode", "ordered")),
                "requires": requires_list,
            }
        )
    out.sort(key=lambda row: row["goal_type"])
    return out


@app.get("/travel-route")
def travel_route_preview(
    from_region_id: int = Query(..., description="Start region id (entity's current region)"),
    to_region_id: int = Query(..., description="Destination region id"),
) -> dict[str, Any]:
    """Cheapest path over ``travel_edges`` (same logic as sim)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, key, name, type, parent_id
                  FROM regions
                 ORDER BY id
                """
            )
            rows = cur.fetchall()

    regions_by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        regions_by_id[int(row[0])] = {
            "id": int(row[0]),
            "key": row[1],
            "name": row[2],
            "type": row[3],
            "parent_id": int(row[4]) if row[4] is not None else None,
        }

    if from_region_id not in regions_by_id or to_region_id not in regions_by_id:
        raise HTTPException(status_code=404, detail="Unknown region id")

    segments = route_travel_segments(from_region_id, to_region_id, regions_by_id)

    if segments is None:
        return {
            "segments": None,
            "stop_names": [],
            "reason": "no_route",
        }

    if not segments:
        return {
            "segments": [],
            "stop_names": [],
            "reason": "same_region",
        }

    stop_names: list[str] = [str(segments[0].from_name)]
    for seg in segments:
        stop_names.append(str(seg.to_name))

    return {
        "segments": [asdict(s) for s in segments],
        "stop_names": stop_names,
        "reason": None,
    }


@app.get("/entities")
def list_entities():
    sql = """
        SELECT e.id, e.name, e.type, e.created_at,
               r.name AS race, sr.name AS subrace,
               z.zone AS zone,
               hf.id AS house_id, hf.name AS house_name, eh.rank AS house_rank
        FROM entities e
        LEFT JOIN races r ON r.id = e.race_id
        LEFT JOIN subraces sr ON sr.id = e.subrace_id
        LEFT JOIN entity_zones z ON z.entity_id = e.id
        LEFT JOIN LATERAL (
            SELECT ef.faction_id, ef.rank
            FROM entity_factions ef
            JOIN factions f ON f.id = ef.faction_id
            WHERE ef.entity_id = e.id
              AND f.kind = 'house'
            ORDER BY ef.joined_at
            LIMIT 1
        ) eh ON TRUE
        LEFT JOIN factions hf ON hf.id = eh.faction_id
        ORDER BY e.id
        LIMIT 500
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return _rows_to_dicts(cur)


@app.get("/entities/{entity_id}")
def get_entity(entity_id: int):
    with get_connection() as conn:
        return _entity_or_404(conn, entity_id)


@app.put("/entities/{entity_id}/zone")
def update_entity_zone(entity_id: int, request: EntityZoneUpdate):
    with get_connection() as conn:
        try:
            entity_service.set_entity_zone(
                conn,
                entity_id,
                request.region_id,
                request.zone,
            )
        except entity_service.EntityServiceError as exc:
            _raise_entity_service_error(exc)
        conn.commit()
        return _entity_or_404(conn, entity_id)


@app.post("/entities/{entity_id}/traits/{trait_id}")
def add_entity_trait(entity_id: int, trait_id: int):
    with get_connection() as conn:
        try:
            entity_service.add_entity_trait(conn, entity_id, trait_id)
        except entity_service.EntityServiceError as exc:
            _raise_entity_service_error(exc)
        conn.commit()
        return _entity_or_404(conn, entity_id)


@app.delete("/entities/{entity_id}/traits/{trait_id}")
def remove_entity_trait(entity_id: int, trait_id: int):
    with get_connection() as conn:
        entity_service.remove_entity_trait(conn, entity_id, trait_id)
        conn.commit()
        return _entity_or_404(conn, entity_id)


@app.post("/entities/{entity_id}/factions/{faction_id}")
def add_entity_faction(
    entity_id: int,
    faction_id: int,
    request: EntityFactionUpdate | None = None,
):
    settings = request or EntityFactionUpdate()
    with get_connection() as conn:
        try:
            entity_service.set_entity_faction(
                conn,
                entity_id,
                faction_id,
                settings.rank,
                settings.reputation,
            )
        except entity_service.EntityServiceError as exc:
            _raise_entity_service_error(exc)
        conn.commit()
        return _entity_or_404(conn, entity_id)


@app.delete("/entities/{entity_id}/factions/{faction_id}")
def remove_entity_faction(entity_id: int, faction_id: int):
    with get_connection() as conn:
        entity_service.remove_entity_faction(conn, entity_id, faction_id)
        conn.commit()
        return _entity_or_404(conn, entity_id)


@app.post("/entities/{entity_id}/items/{item_id}")
def add_entity_item(
    entity_id: int,
    item_id: int,
    request: EntityItemUpdate | None = None,
):
    settings = request or EntityItemUpdate()
    with get_connection() as conn:
        try:
            entity_service.add_entity_item(conn, entity_id, item_id, settings.quantity)
        except entity_service.EntityServiceError as exc:
            _raise_entity_service_error(exc)
        conn.commit()
        return _entity_or_404(conn, entity_id)


@app.delete("/entities/{entity_id}/items/{item_id}")
def remove_entity_item(entity_id: int, item_id: int):
    with get_connection() as conn:
        entity_service.remove_entity_item(conn, entity_id, item_id)
        conn.commit()
        return _entity_or_404(conn, entity_id)


@app.post("/entities/{entity_id}/abilities/{ability_id}")
def add_entity_ability(
    entity_id: int,
    ability_id: int,
    request: EntityAbilityUpdate | None = None,
):
    settings = request or EntityAbilityUpdate()
    with get_connection() as conn:
        try:
            entity_service.set_entity_ability(
                conn,
                entity_id,
                ability_id,
                settings.level,
            )
        except entity_service.EntityServiceError as exc:
            _raise_entity_service_error(exc)
        conn.commit()
        return _entity_or_404(conn, entity_id)


@app.delete("/entities/{entity_id}/abilities/{ability_id}")
def remove_entity_ability(entity_id: int, ability_id: int):
    with get_connection() as conn:
        entity_service.remove_entity_ability(conn, entity_id, ability_id)
        conn.commit()
        return _entity_or_404(conn, entity_id)


@app.post("/entities/{entity_id}/goals")
def add_entity_goal(entity_id: int, request: EntityGoalCreate):
    with get_connection() as conn:
        try:
            entity_service.add_entity_goal(
                conn,
                entity_id,
                request.goal_type,
                request.payload,
                request.priority,
                request.urgency,
                request.completion_mode,
                request.parent_goal_id,
                request.interruptible,
                request.deadline_game_tick,
            )
        except entity_service.EntityServiceError as exc:
            _raise_entity_service_error(exc)
        conn.commit()
        return _entity_or_404(conn, entity_id)


@app.delete("/entities/{entity_id}/goals/{goal_id}")
def remove_entity_goal(entity_id: int, goal_id: int):
    with get_connection() as conn:
        entity_service.remove_entity_goal(conn, entity_id, goal_id)
        conn.commit()
        return _entity_or_404(conn, entity_id)


# -------- Factions --------

@app.get("/factions")
def list_factions():
    sql = """
        SELECT f.id, f.name, f.description, f.kind,
               p.id AS parent_id, p.name AS parent_name,
               (SELECT COUNT(*) FROM entity_factions ef WHERE ef.faction_id = f.id)
                   AS member_count,
               (SELECT COUNT(*) FROM factions c WHERE c.parent_id = f.id) AS child_count,
               EXISTS(SELECT 1 FROM houses  h WHERE h.faction_id = f.id) AS is_house
        FROM factions f
        LEFT JOIN factions p ON p.id = f.parent_id
        ORDER BY f.name
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return _rows_to_dicts(cur)


@app.get("/factions/{faction_id}")
def get_faction(faction_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id, f.name, f.description, f.kind,
                       p.id AS parent_id, p.name AS parent_name
                FROM factions f
                LEFT JOIN factions p ON p.id = f.parent_id
                WHERE f.id = %s
                """,
                (faction_id,),
            )
            base = _rows_to_dicts(cur)
            if not base:
                raise HTTPException(status_code=404, detail="Faction not found")
            faction = base[0]

            cur.execute(
                "SELECT id, name, kind FROM factions WHERE parent_id = %s ORDER BY name",
                (faction_id,),
            )
            faction["children"] = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT e.id, e.name, ef.rank AS rank, ef.reputation AS reputation,
                       CASE WHEN f.kind = 'house' THEN 'house' ELSE 'faction' END AS source
                FROM entity_factions ef
                JOIN entities e ON e.id = ef.entity_id
                JOIN factions f ON f.id = ef.faction_id
                WHERE ef.faction_id = %s
                ORDER BY rank, name
                """,
                (faction_id,),
            )
            faction["members"] = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT s.prestige, s.capacity,
                       (SELECT COUNT(*) FROM entity_factions ef
                        WHERE ef.faction_id = s.faction_id) AS current_enrollment,
                       s.min_enrollment_age, s.max_enrollment_age, s.enrollment_length,
                       s.term_start_doy, s.term_end_doy, s.application_deadline_doy,
                       s.entry_requirements
                FROM schools s
                WHERE s.faction_id = %s
                """,
                (faction_id,),
            )
            school_rows = _rows_to_dicts(cur)
            faction["school"] = school_rows[0] if school_rows else None

            cur.execute(
                """
                SELECT default_surname, spawn_min,
                       forced_traits, forced_magic,
                       house_trait_counts, house_trait_weights,
                       normal_trait_weight_mults,
                       magic_type_counts, magic_weights
                FROM houses
                WHERE faction_id = %s
                """,
                (faction_id,),
            )
            house_rows = _rows_to_dicts(cur)
            faction["house"] = house_rows[0] if house_rows else None

            cur.execute(
                """
                SELECT r.id AS region_id, r.name AS region_name, r.type AS region_type,
                       rc.role, rc.since_game_tick, rc.updated_at
                  FROM region_control rc
                  JOIN regions r ON r.id = rc.region_id
                 WHERE rc.faction_id = %s
                 ORDER BY rc.role, r.name
                """,
                (faction_id,),
            )
            faction["regions"] = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT fo.id, fo.order_type, fo.status,
                       fo.entity_id, e.name AS entity_name,
                       fo.region_id, r.name AS region_name,
                       fo.created_at_game_tick, fo.completed_at_game_tick,
                       fo.payload, fo.created_at, fo.updated_at
                  FROM faction_orders fo
                  LEFT JOIN entities e ON e.id = fo.entity_id
                  LEFT JOIN regions r ON r.id = fo.region_id
                 WHERE fo.faction_id = %s
                 ORDER BY fo.id DESC
                 LIMIT 50
                """,
                (faction_id,),
            )
            faction["orders"] = _rows_to_dicts(cur)

    return faction


# -------- Houses --------
#
# A house is `factions.kind = 'house'` plus a row in `houses` (lineage rules)
# plus zero or more members in `entity_factions`. The `id` we expose to the
# frontend is the underlying faction id, so /houses/{id} and /factions/{id}
# agree on identity for the same house.

@app.get("/houses")
def list_houses():
    sql = """
        SELECT f.id, f.name, f.description AS notes,
               h.type, h.default_surname, h.spawn_min,
               (SELECT COUNT(*) FROM entity_factions ef WHERE ef.faction_id = f.id)
                   AS member_count
        FROM factions f
        JOIN houses h ON h.faction_id = f.id
        ORDER BY f.name
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return _rows_to_dicts(cur)


@app.get("/houses/{house_id}")
def get_house(house_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id, f.name, f.description AS notes,
                       h.type, h.default_surname, h.spawn_min,
                       h.forced_traits, h.forced_magic,
                       h.house_trait_counts, h.house_trait_weights,
                       h.normal_trait_weight_mults,
                       h.magic_type_counts, h.magic_weights
                FROM factions f
                JOIN houses h ON h.faction_id = f.id
                WHERE f.id = %s
                """,
                (house_id,),
            )
            base = _rows_to_dicts(cur)
            if not base:
                raise HTTPException(status_code=404, detail="House not found")
            house = base[0]

            cur.execute(
                """
                SELECT e.id, e.name, ef.rank, ef.joined_at,
                       r.name AS race, sr.name AS subrace
                FROM entity_factions ef
                JOIN entities e ON e.id = ef.entity_id
                LEFT JOIN races r ON r.id = e.race_id
                LEFT JOIN subraces sr ON sr.id = e.subrace_id
                WHERE ef.faction_id = %s
                ORDER BY
                    CASE ef.rank
                        WHEN 'patriarch' THEN 0
                        WHEN 'matriarch' THEN 0
                        WHEN 'heir' THEN 1
                        WHEN 'scion' THEN 2
                        WHEN 'member' THEN 3
                        ELSE 4
                    END,
                    e.name
                """,
                (house_id,),
            )
            house["members"] = _rows_to_dicts(cur)

            # Other organizations the house's members belong to — handy for
            # answering "which knight orders / guilds does this family field?"
            cur.execute(
                """
                SELECT f.id, f.name, f.kind, COUNT(*) AS member_count
                FROM entity_factions eh
                JOIN entity_factions ef ON ef.entity_id = eh.entity_id
                JOIN factions f ON f.id = ef.faction_id
                WHERE eh.faction_id = %s
                  AND ef.faction_id <> %s
                GROUP BY f.id, f.name, f.kind
                ORDER BY member_count DESC, f.name
                """,
                (house_id, house_id),
            )
            house["affiliated_factions"] = _rows_to_dicts(cur)

    return house


# -------- Schools --------

@app.get("/schools")
def list_schools():
    sql = """
        SELECT s.faction_id AS id, f.name,
               s.prestige, s.capacity,
               (SELECT COUNT(*) FROM entity_factions ef
                WHERE ef.faction_id = s.faction_id) AS current_enrollment,
               s.min_enrollment_age, s.max_enrollment_age, s.enrollment_length,
               s.term_start_doy, s.term_end_doy, s.application_deadline_doy
        FROM schools s
        JOIN factions f ON f.id = s.faction_id
        ORDER BY s.prestige DESC, f.name
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return _rows_to_dicts(cur)


@app.get("/schools/{school_id}")
def get_school(school_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.faction_id AS id, f.name, f.description,
                       s.prestige, s.capacity,
                       (SELECT COUNT(*) FROM entity_factions ef
                        WHERE ef.faction_id = s.faction_id) AS current_enrollment,
                       s.min_enrollment_age, s.max_enrollment_age, s.enrollment_length,
                       s.term_start_doy, s.term_end_doy, s.application_deadline_doy,
                       s.entry_requirements
                FROM schools s
                JOIN factions f ON f.id = s.faction_id
                WHERE s.faction_id = %s
                """,
                (school_id,),
            )
            base = _rows_to_dicts(cur)
            if not base:
                raise HTTPException(status_code=404, detail="School not found")
            school = base[0]

            cur.execute(
                """
                SELECT e.id AS entity_id, e.name, ef.rank, ef.reputation
                FROM entity_factions ef
                JOIN entities e ON e.id = ef.entity_id
                WHERE ef.faction_id = %s
                ORDER BY ef.rank, e.name
                """,
                (school_id,),
            )
            school["roster"] = _rows_to_dicts(cur)

    return school


# -------- Regions --------

@app.get("/regions")
def list_regions():
    sql = """
        WITH RECURSIVE descendants(root_id, id, path) AS (
            SELECT id, id, ARRAY[id]
              FROM regions
            UNION ALL
            SELECT d.root_id, c.id, d.path || c.id
              FROM descendants d
              JOIN regions c ON c.parent_id = d.id
             WHERE NOT c.id = ANY(d.path)
        ),
        region_counts AS (
            SELECT d.root_id,
                   COUNT(z.entity_id)::int AS total_entity_count
              FROM descendants d
              LEFT JOIN entity_zones z ON z.region_id = d.id
             GROUP BY d.root_id
        )
        SELECT r.id, r.key, r.name, r.type, r.parent_id, p.name AS parent_name,
               r.tick_interval_seconds, r.paused, r.last_tick_at,
               owner.faction_id AS owner_faction_id,
               owner_f.name AS owner_faction_name,
               controller.faction_id AS controller_faction_id,
               controller_f.name AS controller_faction_name,
               (SELECT COUNT(*)::int FROM entity_zones z WHERE z.region_id = r.id)
                   AS direct_entity_count,
               COALESCE(rc.total_entity_count, 0)::int AS entity_count,
               COALESCE(rc.total_entity_count, 0)::int AS total_entity_count,
               (SELECT COUNT(*)::int FROM regions c WHERE c.parent_id = r.id)
                   AS child_count
          FROM regions r
          LEFT JOIN regions p ON p.id = r.parent_id
          LEFT JOIN region_control owner
            ON owner.region_id = r.id AND owner.role = 'owner'
          LEFT JOIN factions owner_f ON owner_f.id = owner.faction_id
          LEFT JOIN region_control controller
            ON controller.region_id = r.id AND controller.role = 'controller'
          LEFT JOIN factions controller_f ON controller_f.id = controller.faction_id
          LEFT JOIN region_counts rc ON rc.root_id = r.id
         ORDER BY COALESCE(p.name, r.name), r.parent_id NULLS FIRST, r.name
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return _rows_to_dicts(cur)


@app.get("/regions/{region_id}")
def get_region(region_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH RECURSIVE descendants(id, path) AS (
                    SELECT id, ARRAY[id]
                      FROM regions
                     WHERE id = %s
                    UNION ALL
                    SELECT c.id, d.path || c.id
                      FROM descendants d
                      JOIN regions c ON c.parent_id = d.id
                     WHERE NOT c.id = ANY(d.path)
                ),
                region_counts AS (
                    SELECT COUNT(z.entity_id)::int AS total_entity_count
                      FROM descendants d
                      LEFT JOIN entity_zones z ON z.region_id = d.id
                )
                SELECT r.id, r.key, r.name, r.type, r.parent_id, p.name AS parent_name,
                       r.tick_interval_seconds, r.paused, r.last_tick_at,
                       owner.faction_id AS owner_faction_id,
                       owner_f.name AS owner_faction_name,
                       controller.faction_id AS controller_faction_id,
                       controller_f.name AS controller_faction_name,
                       (SELECT COUNT(*)::int FROM entity_zones z WHERE z.region_id = r.id)
                           AS direct_entity_count,
                       COALESCE(rc.total_entity_count, 0)::int AS entity_count,
                       COALESCE(rc.total_entity_count, 0)::int AS total_entity_count,
                       (SELECT COUNT(*)::int FROM regions c WHERE c.parent_id = r.id)
                           AS child_count
                  FROM regions r
                  LEFT JOIN regions p ON p.id = r.parent_id
                  LEFT JOIN region_control owner
                    ON owner.region_id = r.id AND owner.role = 'owner'
                  LEFT JOIN factions owner_f ON owner_f.id = owner.faction_id
                  LEFT JOIN region_control controller
                    ON controller.region_id = r.id AND controller.role = 'controller'
                  LEFT JOIN factions controller_f ON controller_f.id = controller.faction_id
                  CROSS JOIN region_counts rc
                 WHERE r.id = %s
                """,
                (region_id, region_id),
            )
            rows = _rows_to_dicts(cur)
            if not rows:
                raise HTTPException(status_code=404, detail="Region not found")
            region = rows[0]

            cur.execute(
                """
                WITH RECURSIVE descendants(id, path) AS (
                    SELECT id, ARRAY[id]
                      FROM regions
                     WHERE id = %s
                    UNION ALL
                    SELECT c.id, d.path || c.id
                      FROM descendants d
                      JOIN regions c ON c.parent_id = d.id
                     WHERE NOT c.id = ANY(d.path)
                )
                SELECT e.id, e.name, z.zone,
                       loc.id AS region_id,
                       loc.key AS region_key,
                       loc.name AS region_name,
                       loc.type AS region_type
                  FROM descendants d
                  JOIN entity_zones z ON z.region_id = d.id
                  JOIN entities e ON e.id = z.entity_id
                  JOIN regions loc ON loc.id = z.region_id
                 ORDER BY loc.name, e.name
                """,
                (region_id,),
            )
            region["residents"] = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT id, key, name, type
                  FROM regions
                 WHERE parent_id = %s
                 ORDER BY name
                """,
                (region_id,),
            )
            region["children"] = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT rc.role, rc.faction_id, f.name AS faction_name,
                       rc.since_game_tick, rc.updated_at
                  FROM region_control rc
                  JOIN factions f ON f.id = rc.faction_id
                 WHERE rc.region_id = %s
                 ORDER BY CASE rc.role WHEN 'owner' THEN 1 ELSE 2 END
                """,
                (region_id,),
            )
            region["control"] = _rows_to_dicts(cur)

    return region


# -------- Items --------

@app.get("/items")
def list_items():
    sql = """
        SELECT i.id, i.name, i.description, i.category,
               (SELECT COALESCE(SUM(ei.quantity), 0)
                  FROM entity_items ei WHERE ei.item_id = i.id) AS total_owned
        FROM items i
        ORDER BY COALESCE(i.category, 'zzz'), i.name
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return _rows_to_dicts(cur)


# -------- Abilities --------

@app.get("/abilities")
def list_abilities():
    sql = """
        SELECT a.id, a.name, a.description, a.type,
               a.cooldown_seconds, a.cost, a.damage,
               (SELECT COUNT(*) FROM entity_abilities ea WHERE ea.ability_id = a.id) AS holders
        FROM abilities a
        ORDER BY a.type, a.name
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return _rows_to_dicts(cur)


# -------- Traits --------

@app.get("/traits")
def list_traits():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id, t.name, t.description,
                       (SELECT COUNT(*) FROM entity_traits et WHERE et.trait_id = t.id) AS holders
                FROM traits t
                ORDER BY t.name
                """
            )
            traits = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT tsm.trait_id, s.name AS stat, tsm.modifier_type, tsm.value
                FROM trait_stat_modifiers tsm
                JOIN stats s ON s.id = tsm.stat_id
                """
            )
            mods_by_trait: dict[int, list[dict]] = {}
            for row in _rows_to_dicts(cur):
                mods_by_trait.setdefault(int(row["trait_id"]), []).append(
                    {"stat": row["stat"], "type": row["modifier_type"], "value": float(row["value"])}
                )

            cur.execute(
                """
                SELECT ta.trait_id, a.id AS ability_id, a.name AS ability_name
                FROM trait_abilities ta
                JOIN abilities a ON a.id = ta.ability_id
                """
            )
            abilities_by_trait: dict[int, list[dict]] = {}
            for row in _rows_to_dicts(cur):
                abilities_by_trait.setdefault(int(row["trait_id"]), []).append(
                    {"id": row["ability_id"], "name": row["ability_name"]}
                )

    for t in traits:
        tid = int(t["id"])
        t["modifiers"] = mods_by_trait.get(tid, [])
        t["grants_abilities"] = abilities_by_trait.get(tid, [])
    return traits


# -------- Races --------

@app.get("/races")
def list_races():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, r.name,
                       (SELECT COUNT(*) FROM entities e WHERE e.race_id = r.id) AS entity_count
                FROM races r
                ORDER BY r.name
                """
            )
            races = _rows_to_dicts(cur)

            cur.execute("SELECT id, race_id, name FROM subraces ORDER BY name")
            subs_by_race: dict[int, list[dict]] = {}
            for row in _rows_to_dicts(cur):
                subs_by_race.setdefault(int(row["race_id"]), []).append(
                    {"id": row["id"], "name": row["name"]}
                )

    for r in races:
        r["subraces"] = subs_by_race.get(int(r["id"]), [])
    return races

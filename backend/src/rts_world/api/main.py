from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ..db.db import get_connection

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


@app.get("/")
def root():
    return {"name": "Fantasy Sim Game State API", "status": "ok"}


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

@app.get("/entities")
def list_entities():
    sql = """
        SELECT e.id, e.name, e.type, e.created_at,
               r.name AS race, sr.name AS subrace,
               z.zone AS zone
        FROM entities e
        LEFT JOIN races r ON r.id = e.race_id
        LEFT JOIN subraces sr ON sr.id = e.subrace_id
        LEFT JOIN entity_zones z ON z.entity_id = e.id
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
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.id, e.name, e.type, e.created_at,
                       r.name AS race, sr.name AS subrace
                FROM entities e
                LEFT JOIN races r ON r.id = e.race_id
                LEFT JOIN subraces sr ON sr.id = e.subrace_id
                WHERE e.id = %s
                """,
                (entity_id,),
            )
            base_rows = _rows_to_dicts(cur)
            if not base_rows:
                raise HTTPException(status_code=404, detail="Entity not found")
            entity = base_rows[0]

            cur.execute(
                """
                SELECT t.id, t.name, t.description
                FROM entity_traits et
                JOIN traits t ON t.id = et.trait_id
                WHERE et.entity_id = %s
                ORDER BY t.name
                """,
                (entity_id,),
            )
            entity["traits"] = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT f.id, f.name, ef.rank, ef.reputation
                FROM entity_factions ef
                JOIN factions f ON f.id = ef.faction_id
                WHERE ef.entity_id = %s
                ORDER BY f.name
                """,
                (entity_id,),
            )
            entity["factions"] = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT i.id, i.name, i.category, i.description, ei.quantity
                FROM entity_items ei
                JOIN items i ON i.id = ei.item_id
                WHERE ei.entity_id = %s
                ORDER BY i.name
                """,
                (entity_id,),
            )
            entity["items"] = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT a.id, a.name, a.description, a.type, a.cooldown_seconds,
                       a.cost, a.damage, ea.level, ea.last_used_at
                FROM entity_abilities ea
                JOIN abilities a ON a.id = ea.ability_id
                WHERE ea.entity_id = %s
                ORDER BY a.name
                """,
                (entity_id,),
            )
            entity["abilities"] = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT s.faction_id AS school_id, f.name AS school_name,
                       es.status, es.enrolled_at
                FROM entity_schools es
                JOIN schools s ON s.faction_id = es.school_id
                JOIN factions f ON f.id = s.faction_id
                WHERE es.entity_id = %s
                ORDER BY es.enrolled_at DESC
                """,
                (entity_id,),
            )
            entity["schools"] = _rows_to_dicts(cur)

            cur.execute(
                "SELECT zone, updated_at FROM entity_zones WHERE entity_id = %s",
                (entity_id,),
            )
            zone_rows = _rows_to_dicts(cur)
            entity["zone"] = zone_rows[0] if zone_rows else None

            cur.execute(
                "SELECT x, y, z, updated_at FROM entity_positions WHERE entity_id = %s",
                (entity_id,),
            )
            pos_rows = _rows_to_dicts(cur)
            entity["position"] = pos_rows[0] if pos_rows else None

            cur.execute(
                """
                SELECT r.target_entity_id AS entity_id, te.name AS entity_name,
                       r.opinion, r.last_updated
                FROM relationships r
                JOIN entities te ON te.id = r.target_entity_id
                WHERE r.subject_entity_id = %s
                ORDER BY r.opinion DESC
                """,
                (entity_id,),
            )
            entity["relationships"] = _rows_to_dicts(cur)

    return entity


# -------- Factions --------

@app.get("/factions")
def list_factions():
    sql = """
        SELECT f.id, f.name, f.description,
               p.id AS parent_id, p.name AS parent_name,
               (SELECT COUNT(*) FROM entity_factions ef WHERE ef.faction_id = f.id) AS member_count,
               (SELECT COUNT(*) FROM factions c WHERE c.parent_id = f.id) AS child_count,
               EXISTS(SELECT 1 FROM schools s WHERE s.faction_id = f.id) AS is_school
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
                SELECT f.id, f.name, f.description,
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
                "SELECT id, name FROM factions WHERE parent_id = %s ORDER BY name",
                (faction_id,),
            )
            faction["children"] = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT e.id, e.name, ef.rank, ef.reputation
                FROM entity_factions ef
                JOIN entities e ON e.id = ef.entity_id
                WHERE ef.faction_id = %s
                ORDER BY ef.rank, e.name
                """,
                (faction_id,),
            )
            faction["members"] = _rows_to_dicts(cur)

            cur.execute(
                """
                SELECT prestige, capacity, current_enrollment,
                       min_enrollment_age, max_enrollment_age, enrollment_length,
                       term_start_doy, term_end_doy, application_deadline_doy,
                       entry_requirements
                FROM schools
                WHERE faction_id = %s
                """,
                (faction_id,),
            )
            school_rows = _rows_to_dicts(cur)
            faction["school"] = school_rows[0] if school_rows else None

    return faction


# -------- Schools --------

@app.get("/schools")
def list_schools():
    sql = """
        SELECT s.faction_id AS id, f.name,
               s.prestige, s.capacity, s.current_enrollment,
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
                       s.prestige, s.capacity, s.current_enrollment,
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
                SELECT es.entity_id, e.name, es.status, es.enrolled_at
                FROM entity_schools es
                JOIN entities e ON e.id = es.entity_id
                WHERE es.school_id = %s
                ORDER BY es.status, e.name
                """,
                (school_id,),
            )
            school["roster"] = _rows_to_dicts(cur)

    return school


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

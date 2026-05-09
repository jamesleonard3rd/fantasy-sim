"""
Seed the database from JSON game-data files.

Layout (all under <repo>/game_data):
  races/races.json          -> races + nested subraces
  factions/factions.json    -> factions (with optional parent name)
  stats/stats.json          -> stats lookup
  traits/traits.json        -> traits (+ modifier rows, + ability links)
  abilities/abilities.json  -> abilities
  items/items.json          -> items
  schools/*.json            -> per-school detail (one file per school)

Schema is still applied from schema.sql. All inserts are idempotent.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import psycopg

from .db import get_connection


# Repo root (…/fantasy-sim) — game_data lives here, not under backend/
DB_DIR = Path(__file__).parent
PROJECT_DIR = DB_DIR.parent.parent.parent.parent

GAME_DATA = PROJECT_DIR / "game_data"
SCHEMA_FILE = DB_DIR / "schema.sql"

RACES_FILE = GAME_DATA / "races" / "races.json"
FACTIONS_FILE = GAME_DATA / "factions" / "factions.json"
STATS_FILE = GAME_DATA / "stats" / "stats.json"
TRAITS_FILE = GAME_DATA / "traits" / "traits.json"
ABILITIES_FILE = GAME_DATA / "abilities" / "abilities.json"
ITEMS_FILE = GAME_DATA / "items" / "items.json"
SCHOOLS_DIR = GAME_DATA / "schools"
HOUSES_FILE = GAME_DATA / "houses" / "templates.json"


# ---------- helpers ----------

def _load_json(path: Path) -> Any:
    if not path.exists():
        print(f"  WARN missing JSON file: {path.relative_to(PROJECT_DIR)}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  WARN invalid JSON in {path.name}: {e}")
        return None


def _run_sql_file(conn: psycopg.Connection, filepath: Path) -> None:
    print(f"Applying {filepath.name}...")
    sql = filepath.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"  OK {filepath.name}")


def _fetch_lookup(conn: psycopg.Connection, table: str) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT id, name FROM {table}")
        return {row[1]: int(row[0]) for row in cur.fetchall()}


# ---------- loaders ----------

def seed_races(conn: psycopg.Connection) -> None:
    print("Seeding races...")
    data = _load_json(RACES_FILE)
    if not data:
        return

    races: Iterable[dict[str, Any]] = data.get("races", [])
    with conn.cursor() as cur:
        for race in races:
            cur.execute(
                "INSERT INTO races (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                (race["name"],),
            )

        race_ids = _fetch_lookup(conn, "races")

        for race in races:
            race_id = race_ids.get(race["name"])
            if race_id is None:
                continue
            for sub in race.get("subraces", []) or []:
                cur.execute(
                    """
                    INSERT INTO subraces (name, race_id) VALUES (%s, %s)
                    ON CONFLICT (race_id, name) DO NOTHING
                    """,
                    (sub["name"], race_id),
                )

    conn.commit()
    print(f"  OK races + subraces")


def seed_factions(conn: psycopg.Connection) -> None:
    print("Seeding factions...")
    data = _load_json(FACTIONS_FILE)
    if not data:
        return

    factions: list[dict[str, Any]] = list(data.get("factions", []))

    with conn.cursor() as cur:
        for f in factions:
            cur.execute(
                """
                INSERT INTO factions (name, description) VALUES (%s, %s)
                ON CONFLICT (name) DO NOTHING
                """,
                (f["name"], f.get("description")),
            )

        for f in factions:
            parent_name = f.get("parent")
            if not parent_name:
                continue
            cur.execute(
                """
                UPDATE factions SET parent_id = (
                    SELECT id FROM factions WHERE name = %s
                )
                WHERE name = %s
                """,
                (parent_name, f["name"]),
            )

    conn.commit()
    print(f"  OK {len(factions)} factions")


def seed_stats(conn: psycopg.Connection) -> None:
    print("Seeding stats...")
    data = _load_json(STATS_FILE)
    if not data:
        return

    stats = data.get("stats", [])
    with conn.cursor() as cur:
        for s in stats:
            cur.execute(
                """
                INSERT INTO stats (name, description) VALUES (%s, %s)
                ON CONFLICT (name) DO NOTHING
                """,
                (s["name"], s.get("description")),
            )
    conn.commit()
    print(f"  OK {len(stats)} stats")


def seed_abilities(conn: psycopg.Connection) -> None:
    print("Seeding abilities...")
    data = _load_json(ABILITIES_FILE)
    if not data:
        return

    abilities = data.get("abilities", [])
    with conn.cursor() as cur:
        for a in abilities:
            cur.execute(
                """
                INSERT INTO abilities (
                    name, description, type,
                    cooldown_seconds, cost, damage
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO NOTHING
                """,
                (
                    a["name"],
                    a.get("description"),
                    a["type"],
                    int(a.get("cooldown_seconds", 0)),
                    int(a.get("cost", 0)),
                    int(a.get("damage", 0)),
                ),
            )
    conn.commit()
    print(f"  OK {len(abilities)} abilities")


def seed_items(conn: psycopg.Connection) -> None:
    print("Seeding items...")
    data = _load_json(ITEMS_FILE)
    if not data:
        return

    items = data.get("items", [])
    with conn.cursor() as cur:
        for it in items:
            cur.execute(
                """
                INSERT INTO items (name, description, category) VALUES (%s, %s, %s)
                ON CONFLICT (name) DO NOTHING
                """,
                (it["name"], it.get("description"), it.get("category")),
            )
    conn.commit()
    print(f"  OK {len(items)} items")


def seed_traits(conn: psycopg.Connection) -> None:
    """Insert traits, plus stat modifiers and ability grants for each trait."""
    print("Seeding traits...")
    data = _load_json(TRAITS_FILE)
    if not data:
        return

    traits = data.get("traits", [])

    with conn.cursor() as cur:
        for t in traits:
            cur.execute(
                """
                INSERT INTO traits (name, description) VALUES (%s, %s)
                ON CONFLICT (name) DO NOTHING
                """,
                (t["name"], t.get("description")),
            )

    trait_ids = _fetch_lookup(conn, "traits")
    stat_ids = _fetch_lookup(conn, "stats")
    ability_ids = _fetch_lookup(conn, "abilities")

    mod_count = 0
    link_count = 0
    with conn.cursor() as cur:
        for t in traits:
            trait_id = trait_ids.get(t["name"])
            if trait_id is None:
                continue

            for mod in t.get("modifiers", []) or []:
                stat_name = mod.get("stat")
                mod_type = mod.get("type")
                value = mod.get("value")
                if not stat_name or mod_type not in ("add", "mult") or value is None:
                    continue
                stat_id = stat_ids.get(stat_name)
                if stat_id is None:
                    print(f"  WARN trait '{t['name']}' references unknown stat '{stat_name}'")
                    continue
                cur.execute(
                    """
                    INSERT INTO trait_stat_modifiers (trait_id, stat_id, modifier_type, value)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (trait_id, stat_id, modifier_type) DO NOTHING
                    """,
                    (trait_id, stat_id, mod_type, value),
                )
                mod_count += 1

            for ability_name in t.get("abilities", []) or []:
                if not ability_name:
                    continue
                ability_id = ability_ids.get(ability_name)
                if ability_id is None:
                    print(
                        f"  WARN trait '{t['name']}' references unknown ability '{ability_name}'"
                    )
                    continue
                cur.execute(
                    """
                    INSERT INTO trait_abilities (trait_id, ability_id) VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (trait_id, ability_id),
                )
                link_count += 1

    conn.commit()
    print(f"  OK {len(traits)} traits ({mod_count} modifiers, {link_count} ability links)")


def seed_houses(conn: psycopg.Connection) -> None:
    """Insert noble houses.

    A house is a faction (`factions.kind = 'house'`) with extra lineage
    rules in the `houses` detail table (mirrors how schools are modelled).
    For each house template we:

      1. Upsert the `factions` row (name, description, kind='house').
      2. Upsert the `houses` row keyed by that faction's id.

    The optional ``type`` field from the template is folded into the
    `factions.description` if no `notes` block is supplied; otherwise
    `notes` wins (it's the authored copy).
    """
    print("Seeding houses...")
    data = _load_json(HOUSES_FILE)
    if not data:
        return

    houses = data.get("houses", [])
    with conn.cursor() as cur:
        for h in houses:
            cur.execute(
                """
                INSERT INTO factions (name, description, kind)
                VALUES (%s, %s, 'house')
                ON CONFLICT (name) DO UPDATE
                    SET description = EXCLUDED.description,
                        kind = 'house'
                RETURNING id
                """,
                (h["name"], h.get("notes")),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"Failed to upsert faction for house {h['name']}")
            faction_id = int(row[0])

            cur.execute(
                """
                INSERT INTO houses (
                    faction_id, type, default_surname, spawn_min,
                    forced_traits, forced_magic,
                    house_trait_counts, house_trait_weights,
                    normal_trait_weight_mults,
                    magic_type_counts, magic_weights
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s,
                    %s, %s
                )
                ON CONFLICT (faction_id) DO UPDATE SET
                    type = EXCLUDED.type,
                    default_surname = EXCLUDED.default_surname,
                    spawn_min = EXCLUDED.spawn_min,
                    forced_traits = EXCLUDED.forced_traits,
                    forced_magic = EXCLUDED.forced_magic,
                    house_trait_counts = EXCLUDED.house_trait_counts,
                    house_trait_weights = EXCLUDED.house_trait_weights,
                    normal_trait_weight_mults = EXCLUDED.normal_trait_weight_mults,
                    magic_type_counts = EXCLUDED.magic_type_counts,
                    magic_weights = EXCLUDED.magic_weights
                """,
                (
                    faction_id,
                    h.get("type"),
                    h.get("default_surname"),
                    h.get("spawn_min"),
                    json.dumps(h.get("forced_traits", [])),
                    json.dumps(h.get("forced_magic", [])),
                    json.dumps(h.get("house_trait_counts", {})),
                    json.dumps(h.get("house_trait_weights", {})),
                    json.dumps(h.get("normal_trait_weight_mults", {})),
                    json.dumps(h.get("magic_type_counts", {})),
                    json.dumps(h.get("magic_weights", {})),
                ),
            )
    conn.commit()
    print(f"  OK {len(houses)} houses")


def seed_schools(conn: psycopg.Connection) -> None:
    print("Seeding schools...")
    if not SCHOOLS_DIR.exists():
        print(f"  WARN schools dir missing: {SCHOOLS_DIR.relative_to(PROJECT_DIR)}")
        return

    count = 0
    for filepath in sorted(SCHOOLS_DIR.glob("*.json")):
        data = _load_json(filepath)
        if not data:
            continue

        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM factions WHERE name = %s",
                (data["faction_name"],),
            )
            row = cur.fetchone()
            if not row:
                print(
                    f"  WARN faction '{data['faction_name']}' missing, skipping {filepath.name}"
                )
                continue
            faction_id = row[0]

            cur.execute(
                """
                INSERT INTO schools (
                    faction_id, prestige, capacity,
                    min_enrollment_age, max_enrollment_age, enrollment_length,
                    term_start_doy, term_end_doy, application_deadline_doy,
                    entry_requirements
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (faction_id) DO NOTHING
                """,
                (
                    faction_id,
                    data["prestige"],
                    data.get("capacity"),
                    data.get("min_enrollment_age"),
                    data.get("max_enrollment_age"),
                    data.get("enrollment_length"),
                    data["term_start_doy"],
                    data["term_end_doy"],
                    data["application_deadline_doy"],
                    json.dumps(data.get("entry_requirements"))
                    if data.get("entry_requirements") is not None
                    else None,
                ),
            )
            count += 1
            print(f"  OK {data['faction_name']}")
    conn.commit()
    print(f"  OK {count} schools")


# ---------- orchestration ----------

def seed_database(*, apply_schema: bool = True) -> None:
    conn = get_connection()
    try:
        if apply_schema:
            _run_sql_file(conn, SCHEMA_FILE)

        # Order matters: races -> factions -> stats -> abilities -> items
        # -> traits -> schools -> houses
        seed_races(conn)
        seed_factions(conn)
        seed_stats(conn)
        seed_abilities(conn)
        seed_items(conn)
        seed_traits(conn)
        seed_schools(conn)
        seed_houses(conn)

        print("\nOK Database seeded successfully!")
    except Exception as e:
        print(f"\nERROR: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    seed_database()

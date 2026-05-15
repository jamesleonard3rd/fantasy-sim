from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import psycopg

from .db import get_connection
from .entities import generate_entity, generate_entity_from_template

PROJECT_DIR = Path(__file__).resolve().parents[4]
GAME_DATA_DIR = PROJECT_DIR / "game_data"
TEMPLATES_PATH = GAME_DATA_DIR / "entities" / "templates.json"


def load_templates() -> Dict[str, Any]:
    if not TEMPLATES_PATH.exists():
        raise FileNotFoundError(f"Entity templates file not found: {TEMPLATES_PATH}")
    return dict(json.loads(TEMPLATES_PATH.read_text()))


def fetch_lookup(conn: psycopg.Connection, table: str) -> Dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT id, name FROM {table}")
        return {row[1]: row[0] for row in cur.fetchall()}


def fetch_house_lookup(conn: psycopg.Connection) -> Dict[str, int]:
    """Map house name -> faction_id.

    Houses are factions (`factions.kind = 'house'`); the lineage rules table
    is keyed by `faction_id`. So the lookup we need joins both.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.name, f.id
            FROM factions f
            JOIN houses h ON h.faction_id = f.id
            """
        )
        return {row[0]: int(row[1]) for row in cur.fetchall()}


def insert_entity(conn: psycopg.Connection, name: str, race_id: int, subrace_id: int | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entities (name, race_id, subrace_id) VALUES (%s, %s, %s) RETURNING id",
            (name, race_id, subrace_id),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Failed to insert entity")
        return int(row[0])


def insert_entity_traits(conn: psycopg.Connection, entity_id: int, trait_names: List[str], trait_lookup: Dict[str, int]) -> None:
    if not trait_names:
        return
    values: List[Tuple[int, int]] = []
    for t in trait_names:
        trait_id = trait_lookup.get(t)
        if trait_id is None:
            raise ValueError(f"Unknown trait '{t}' for entity_id {entity_id}")
        values.append((entity_id, trait_id))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO entity_traits (entity_id, trait_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            values,
        )


def insert_entity_house(
    conn: psycopg.Connection,
    entity_id: int,
    house_name: str | None,
    role: str | None,
    house_lookup: Dict[str, int],
) -> None:
    """Set the entity's house as a house faction membership."""
    if not house_name:
        return
    house_id = house_lookup.get(house_name)
    if house_id is None:
        raise ValueError(
            f"Unknown house '{house_name}' for entity_id {entity_id}; "
            "did you run seed_houses() first?"
        )
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM entity_factions ef
            USING factions f
            WHERE ef.faction_id = f.id
              AND f.kind = 'house'
              AND ef.entity_id = %s
              AND ef.faction_id <> %s
            """,
            (entity_id, house_id),
        )
        cur.execute(
            """
            INSERT INTO entity_factions (entity_id, faction_id, rank, reputation)
            VALUES (%s, %s, %s, 0)
            ON CONFLICT (entity_id, faction_id) DO UPDATE
                SET rank = EXCLUDED.rank
            """,
            (entity_id, house_id, role or "member"),
        )


def insert_entity_region(
    conn: psycopg.Connection,
    entity_id: int,
    region_name: str | None,
    region_lookup: Dict[str, int],
) -> None:
    if not region_name:
        return
    region_id = region_lookup.get(region_name)
    if region_id is None:
        raise ValueError(
            f"Unknown region '{region_name}' for entity_id {entity_id}; "
            "did you run seed_regions() first?"
        )
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
            (entity_id, region_name, region_id),
        )


KINSHIP_RELATIONSHIP_TYPES = {
    "parent",
    "child",
    "father",
    "mother",
    "sibling",
    "spouse",
}


def _relationship_source_type(relationship_type: str) -> str:
    if relationship_type in KINSHIP_RELATIONSHIP_TYPES:
        return "kinship"
    return "manual"


def insert_relationships(conn: psycopg.Connection, rels: List[Dict[str, Any]], id_map: Dict[str, int]) -> None:
    if not rels:
        return
    rows: List[Tuple[int, int, int]] = []
    term_rows: List[Tuple[int, int, str, str, str, int, str]] = []
    for r in rels:
        frm = id_map.get(r["from"])
        to = id_map.get(r["to"])
        if frm is None or to is None:
            raise ValueError(f"Relationship references unknown template ids: {r}")
        opinion = int(r.get("opinion", 0))
        relationship_type = str(r.get("type", "manual"))
        rows.append((frm, to, opinion))
        term_rows.append(
            (
                frm,
                to,
                _relationship_source_type(relationship_type),
                relationship_type,
                "template",
                opinion,
                json.dumps({"template_type": relationship_type}),
            )
        )
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO relationships (subject_entity_id, target_entity_id, opinion, last_updated) "
            "VALUES (%s, %s, %s, NOW()) "
            "ON CONFLICT (subject_entity_id, target_entity_id) DO UPDATE "
            "SET opinion = EXCLUDED.opinion, last_updated = NOW()",
            rows,
        )
        cur.executemany(
            """
            INSERT INTO relationship_terms (
                subject_entity_id, target_entity_id, source_type, source_key,
                source_instance, value, payload, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (
                subject_entity_id, target_entity_id, source_type, source_key,
                source_instance
            ) DO UPDATE
                SET value = EXCLUDED.value,
                    payload = EXCLUDED.payload,
                    updated_at = NOW()
            """,
            term_rows,
        )


def seed_templates(
    conn: psycopg.Connection,
    templates: Dict[str, Any],
    race_lookup: Dict[str, int],
    trait_lookup: Dict[str, int],
    house_lookup: Dict[str, int],
    region_lookup: Dict[str, int],
) -> Dict[str, int]:
    id_map: Dict[str, int] = {}
    for ent in templates.get("entities", []):
        entity_data = generate_entity_from_template(ent)
        template_id = entity_data["id"]
        race_name = entity_data.get("race", "Human")
        race_id = race_lookup.get(race_name)
        if race_id is None:
            raise ValueError(f"Unknown race '{race_name}' in template '{template_id}'")
        entity_id = insert_entity(conn, entity_data["name"], race_id)
        insert_entity_traits(conn, entity_id, entity_data.get("traits", []), trait_lookup)
        insert_entity_house(
            conn,
            entity_id,
            entity_data.get("house"),
            entity_data.get("role"),
            house_lookup,
        )
        insert_entity_region(
            conn,
            entity_id,
            entity_data.get("region"),
            region_lookup,
        )
        id_map[template_id] = entity_id
    insert_relationships(conn, templates.get("relationships", []), id_map)
    return id_map


def seed_random_entities(conn: psycopg.Connection, count: int, race_lookup: Dict[str, int], trait_lookup: Dict[str, int]) -> None:
    for _ in range(count):
        entity_data = generate_entity()
        race_name = entity_data["race"]
        race_id = race_lookup.get(race_name)
        if race_id is None:
            raise ValueError(f"Unknown race '{race_name}' while generating random entity")

        entity_id = insert_entity(conn, entity_data["name"], race_id)
        insert_entity_traits(conn, entity_id, entity_data.get("traits", []), trait_lookup)
        # magic is not stored yet; hook up when schema supports it


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed template and random entities.")
    parser.add_argument("--random-count", type=int, default=0, help="How many random entities to generate.")
    parser.add_argument("--skip-templates", action="store_true", help="Skip inserting template entities.")
    args = parser.parse_args()

    templates = load_templates()

    with get_connection() as conn:
        race_lookup = fetch_lookup(conn, "races")
        trait_lookup = fetch_lookup(conn, "traits")
        house_lookup = fetch_house_lookup(conn)
        region_lookup = fetch_lookup(conn, "regions")

        if not args.skip_templates:
            seed_templates(conn, templates, race_lookup, trait_lookup, house_lookup, region_lookup)

        if args.random_count > 0:
            seed_random_entities(conn, args.random_count, race_lookup, trait_lookup)

        conn.commit()


if __name__ == "__main__":
    main()



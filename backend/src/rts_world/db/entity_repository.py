"""Connection-injected entity persistence helpers.

This module owns SQL for entity detail reads and API-style entity mutations.
Callers own transaction boundaries: functions here do not open connections,
commit, or translate errors into HTTP responses.
"""
from __future__ import annotations

from typing import Any

import psycopg


def _rows_to_dicts(cur: Any) -> list[dict[str, Any]]:
    cols = [c.name for c in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def row_exists(
    conn: psycopg.Connection,
    table: str,
    column: str,
    value: int,
) -> bool:
    with conn.cursor() as cur:
        cur.execute(f"SELECT 1 FROM {table} WHERE {column} = %s", (value,))
        return cur.fetchone() is not None


def get_region_name(conn: psycopg.Connection, region_id: int) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM regions WHERE id = %s", (region_id,))
        row = cur.fetchone()
    return str(row[0]) if row is not None else None


def get_entity_detail(
    conn: psycopg.Connection,
    entity_id: int,
) -> dict[str, Any] | None:
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
            return None
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
            SELECT f.id, f.name, f.kind, ef.rank, ef.reputation
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
            SELECT z.zone, z.region_id, r.name AS region_name, z.updated_at
            FROM entity_zones z
            LEFT JOIN regions r ON r.id = z.region_id
            WHERE z.entity_id = %s
            """,
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

        cur.execute(
            """
            SELECT hf.id, hf.name, hf.description AS notes,
                   h.type, h.default_surname, eh.role, eh.joined_at
            FROM entity_houses eh
            JOIN houses h ON h.faction_id = eh.house_id
            JOIN factions hf ON hf.id = eh.house_id
            WHERE eh.entity_id = %s
            """,
            (entity_id,),
        )
        house_rows = _rows_to_dicts(cur)
        entity["house"] = house_rows[0] if house_rows else None
        entity["houses"] = house_rows

    return entity


def set_entity_zone(
    conn: psycopg.Connection,
    entity_id: int,
    region_id: int,
    zone: str,
) -> None:
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
            (entity_id, zone, region_id),
        )


def add_entity_trait(
    conn: psycopg.Connection,
    entity_id: int,
    trait_id: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_traits (entity_id, trait_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (entity_id, trait_id),
        )


def remove_entity_trait(
    conn: psycopg.Connection,
    entity_id: int,
    trait_id: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM entity_traits WHERE entity_id = %s AND trait_id = %s",
            (entity_id, trait_id),
        )


def set_entity_faction(
    conn: psycopg.Connection,
    entity_id: int,
    faction_id: int,
    rank: str,
    reputation: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_factions (entity_id, faction_id, rank, reputation)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (entity_id, faction_id) DO UPDATE
                SET rank = EXCLUDED.rank,
                    reputation = EXCLUDED.reputation
            """,
            (entity_id, faction_id, rank, reputation),
        )


def remove_entity_faction(
    conn: psycopg.Connection,
    entity_id: int,
    faction_id: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM entity_factions WHERE entity_id = %s AND faction_id = %s",
            (entity_id, faction_id),
        )


def add_entity_item(
    conn: psycopg.Connection,
    entity_id: int,
    item_id: int,
    quantity: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_items (entity_id, item_id, quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (entity_id, item_id) DO UPDATE
                SET quantity = entity_items.quantity + EXCLUDED.quantity
            """,
            (entity_id, item_id, quantity),
        )


def remove_entity_item(
    conn: psycopg.Connection,
    entity_id: int,
    item_id: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM entity_items WHERE entity_id = %s AND item_id = %s",
            (entity_id, item_id),
        )


def set_entity_ability(
    conn: psycopg.Connection,
    entity_id: int,
    ability_id: int,
    level: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_abilities (entity_id, ability_id, level)
            VALUES (%s, %s, %s)
            ON CONFLICT (entity_id, ability_id) DO UPDATE
                SET level = EXCLUDED.level
            """,
            (entity_id, ability_id, level),
        )


def remove_entity_ability(
    conn: psycopg.Connection,
    entity_id: int,
    ability_id: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM entity_abilities WHERE entity_id = %s AND ability_id = %s",
            (entity_id, ability_id),
        )

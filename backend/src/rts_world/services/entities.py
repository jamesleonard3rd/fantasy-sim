"""Entity domain operations shared by API and backend orchestration.

The functions in this module validate domain preconditions and delegate SQL to
the entity repository. They are transaction-neutral: callers decide when to
commit or roll back.
"""
from __future__ import annotations

import psycopg

from ..db import entity_repository as entities_repo


class EntityServiceError(Exception):
    """Base class for entity service failures."""

    detail = "Entity operation failed"


class EntityNotFound(EntityServiceError):
    detail = "Entity not found"


class RegionNotFound(EntityServiceError):
    detail = "Region not found"


class RelatedRecordNotFound(EntityServiceError):
    detail = "Related record not found"


class TraitNotFound(RelatedRecordNotFound):
    detail = "Trait not found"


class FactionNotFound(RelatedRecordNotFound):
    detail = "Faction not found"


class ItemNotFound(RelatedRecordNotFound):
    detail = "Item not found"


class AbilityNotFound(RelatedRecordNotFound):
    detail = "Ability not found"


def _require_exists(
    conn: psycopg.Connection,
    table: str,
    column: str,
    value: int,
    error: type[EntityServiceError],
) -> None:
    if not entities_repo.row_exists(conn, table, column, value):
        raise error()


def _require_entity(conn: psycopg.Connection, entity_id: int) -> None:
    _require_exists(conn, "entities", "id", entity_id, EntityNotFound)


def get_entity_detail(
    conn: psycopg.Connection,
    entity_id: int,
) -> dict | None:
    return entities_repo.get_entity_detail(conn, entity_id)


def set_entity_zone(
    conn: psycopg.Connection,
    entity_id: int,
    region_id: int,
    zone: str | None = None,
) -> None:
    _require_entity(conn, entity_id)
    region_name = entities_repo.get_region_name(conn, region_id)
    if region_name is None:
        raise RegionNotFound()

    zone_label = zone.strip() if zone else region_name
    entities_repo.set_entity_zone(conn, entity_id, region_id, zone_label)


def add_entity_trait(
    conn: psycopg.Connection,
    entity_id: int,
    trait_id: int,
) -> None:
    _require_entity(conn, entity_id)
    _require_exists(conn, "traits", "id", trait_id, TraitNotFound)
    entities_repo.add_entity_trait(conn, entity_id, trait_id)


def remove_entity_trait(
    conn: psycopg.Connection,
    entity_id: int,
    trait_id: int,
) -> None:
    entities_repo.remove_entity_trait(conn, entity_id, trait_id)


def set_entity_faction(
    conn: psycopg.Connection,
    entity_id: int,
    faction_id: int,
    rank: str,
    reputation: int,
) -> None:
    _require_entity(conn, entity_id)
    _require_exists(conn, "factions", "id", faction_id, FactionNotFound)
    entities_repo.set_entity_faction(conn, entity_id, faction_id, rank, reputation)


def remove_entity_faction(
    conn: psycopg.Connection,
    entity_id: int,
    faction_id: int,
) -> None:
    entities_repo.remove_entity_faction(conn, entity_id, faction_id)


def add_entity_item(
    conn: psycopg.Connection,
    entity_id: int,
    item_id: int,
    quantity: int,
) -> None:
    _require_entity(conn, entity_id)
    _require_exists(conn, "items", "id", item_id, ItemNotFound)
    entities_repo.add_entity_item(conn, entity_id, item_id, quantity)


def remove_entity_item(
    conn: psycopg.Connection,
    entity_id: int,
    item_id: int,
) -> None:
    entities_repo.remove_entity_item(conn, entity_id, item_id)


def set_entity_ability(
    conn: psycopg.Connection,
    entity_id: int,
    ability_id: int,
    level: int,
) -> None:
    _require_entity(conn, entity_id)
    _require_exists(conn, "abilities", "id", ability_id, AbilityNotFound)
    entities_repo.set_entity_ability(conn, entity_id, ability_id, level)


def remove_entity_ability(
    conn: psycopg.Connection,
    entity_id: int,
    ability_id: int,
) -> None:
    entities_repo.remove_entity_ability(conn, entity_id, ability_id)

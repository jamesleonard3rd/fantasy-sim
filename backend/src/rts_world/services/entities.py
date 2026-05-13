"""Entity domain operations shared by API and backend orchestration.

The functions in this module validate domain preconditions and delegate SQL to
the entity repository. They are transaction-neutral: callers decide when to
commit or roll back.
"""
from __future__ import annotations

from typing import Any

import psycopg

from ..db import entity_repository as entities_repo
from ..sim.goal_templates import goal_templates


class EntityServiceError(Exception):
    """Base class for entity service failures."""

    detail = "Entity operation failed"
    status_code = 400


class EntityNotFound(EntityServiceError):
    detail = "Entity not found"
    status_code = 404


class RegionNotFound(EntityServiceError):
    detail = "Region not found"
    status_code = 404


class RelatedRecordNotFound(EntityServiceError):
    detail = "Related record not found"
    status_code = 404


class TraitNotFound(RelatedRecordNotFound):
    detail = "Trait not found"


class FactionNotFound(RelatedRecordNotFound):
    detail = "Faction not found"


class ItemNotFound(RelatedRecordNotFound):
    detail = "Item not found"


class AbilityNotFound(RelatedRecordNotFound):
    detail = "Ability not found"


class GoalsNotAvailable(EntityServiceError):
    detail = "Goal storage is not available"
    status_code = 500


class ParentGoalNotFound(EntityServiceError):
    detail = "Parent goal not found"
    status_code = 404


class InvalidGoalCompletionMode(EntityServiceError):
    detail = "Invalid completion mode"


class InvalidGoalType(EntityServiceError):
    detail = "Goal type is required"


_COMPLETION_MODES = frozenset({"ordered", "any_order", "all_required", "optional"})


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


class UnknownGoalType(EntityServiceError):
    detail = "Goal type is not available"


class MissingGoalPayloadField(EntityServiceError):
    detail = "Goal payload is missing required fields"


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


def add_entity_goal(
    conn: psycopg.Connection,
    entity_id: int,
    goal_type: str,
    payload: dict[str, Any] | None,
    priority: int,
    urgency: int,
    completion_mode: str,
    parent_goal_id: int | None,
    interruptible: bool,
    deadline_game_tick: int | None,
) -> None:
    _require_entity(conn, entity_id)
    if not entities_repo.entity_goals_table_exists(conn):
        raise GoalsNotAvailable()
    cleaned_type = goal_type.strip()
    if not cleaned_type:
        raise InvalidGoalType()
    templates = goal_templates()
    template = templates.get(cleaned_type)
    if template is None:
        raise UnknownGoalType()
    _require_goal_payload_fields(template, payload or {})
    if completion_mode not in _COMPLETION_MODES:
        raise InvalidGoalCompletionMode()
    if parent_goal_id is not None and not entities_repo.entity_goal_exists_for_entity(
        conn, entity_id, parent_goal_id
    ):
        raise ParentGoalNotFound()
    entities_repo.add_entity_goal(
        conn,
        entity_id,
        cleaned_type,
        payload,
        priority,
        urgency,
        completion_mode,
        parent_goal_id,
        interruptible,
        deadline_game_tick,
    )


def remove_entity_goal(
    conn: psycopg.Connection,
    entity_id: int,
    goal_id: int,
) -> None:
    entities_repo.remove_entity_goal(conn, entity_id, goal_id)


def _require_goal_payload_fields(
    template: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    requirements = template.get("requires", [])
    if isinstance(requirements, str):
        requirements = [requirements]
    if not isinstance(requirements, list):
        return
    missing = [
        field
        for field in requirements
        if isinstance(field, str) and payload.get(field) is None
    ]
    if missing:
        raise MissingGoalPayloadField()

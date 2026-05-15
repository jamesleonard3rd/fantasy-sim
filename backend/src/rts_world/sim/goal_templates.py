"""Data-driven parent goal expansion recipes."""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .state import RegionState

PROJECT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_TEMPLATES_FILE = PROJECT_DIR / "game_data" / "goals" / "templates.json"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
ALLOWED_CONDITIONS = {
    "target_region_exists",
    "entity_not_in_target_region",
    "registration_tick_exists",
    "starts_at_exists",
}

MISSING = object()


class GoalTemplateError(ValueError):
    """Raised when a goal template file is structurally invalid."""


def expand_goal_template(
    state: RegionState,
    entity: dict[str, Any],
    goal: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return child goals for a parent goal, or an empty list if none apply."""
    if goal.get("id") is None or goal.get("status") in TERMINAL_STATUSES:
        return []
    if _has_incomplete_children(state.goals_by_entity_id.get(int(entity["id"]), []), goal):
        return []

    goal_type = str(goal.get("goal_type"))

    if goal_type == "travel_to_region":
        template = goal_templates().get(goal_type)
        if template is None:
            return []
        context = _context_for(state, entity, goal)
        if not _requirements_met(template, context):
            return []
        return _expand_travel_to_region_route(state, entity, goal, context)

    template = goal_templates().get(goal_type)
    if template is None:
        return []

    context = _context_for(state, entity, goal)
    if not _requirements_met(template, context):
        return []

    children: list[dict[str, Any]] = []
    order = 1
    for step in template.get("steps", []):
        if not _conditions_match(step.get("when"), context):
            continue
        payload = _resolve_payload(step.get("payload", {}), context)
        if payload is MISSING:
            continue
        children.append(
            _child_goal(
                goal,
                str(step["goal_type"]),
                order,
                payload,
                completion_mode=str(template.get("completion_mode", "ordered")),
            )
        )
        order += 1
    return children


def _expand_travel_to_region_route(
    state: RegionState,
    entity: dict[str, Any],
    goal: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Insert ordered ``travel_segment`` children from ``travel_edges``, when possible."""
    from .travel import route_travel_segments

    parent_id = int(goal["id"])
    entity_id = int(entity["id"])
    goals = state.goals_by_entity_id.get(entity_id, [])
    if any(g.get("parent_goal_id") == parent_id for g in goals):
        return []

    target = context.get("target_region_id")
    if target is None:
        return []
    target_int = int(target)
    cur = entity.get("region_id")
    if cur is not None and int(cur) == target_int:
        return []

    payload = goal.get("payload") or {}
    if "duration_ticks" in payload:
        return []

    route = route_travel_segments(
        int(cur) if cur is not None else None,
        target_int,
        state.regions_by_id,
    )
    if route:
        tmpl = goal_templates().get("travel_to_region") or {}
        completion_mode = str(tmpl.get("completion_mode", "ordered"))
        children: list[dict[str, Any]] = []
        for order, seg in enumerate(route, start=1):
            children.append(
                _child_goal(
                    goal,
                    "travel_segment",
                    order,
                    {
                        "from_region_id": seg.from_region_id,
                        "to_region_id": seg.to_region_id,
                        "duration_ticks": seg.duration_ticks,
                        "mode": seg.mode,
                        "from_name": seg.from_name,
                        "to_name": seg.to_name,
                    },
                    completion_mode=completion_mode,
                )
            )
        return children

    return []


@lru_cache(maxsize=1)
def goal_templates() -> dict[str, dict[str, Any]]:
    return load_goal_templates(DEFAULT_TEMPLATES_FILE)


def load_goal_templates(path: Path = DEFAULT_TEMPLATES_FILE) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return validate_goal_template_data(data)


def validate_goal_template_data(data: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(data, dict):
        raise GoalTemplateError("goal templates file must contain an object")
    raw_templates = data.get("goal_templates")
    if not isinstance(raw_templates, list):
        raise GoalTemplateError("goal_templates must be a list")

    templates: dict[str, dict[str, Any]] = {}
    for index, template in enumerate(raw_templates):
        if not isinstance(template, dict):
            raise GoalTemplateError(f"goal_templates[{index}] must be an object")
        goal_type = template.get("goal_type")
        if not isinstance(goal_type, str) or not goal_type:
            raise GoalTemplateError(f"goal_templates[{index}].goal_type is required")
        steps = template.get("steps")
        if not isinstance(steps, list):
            raise GoalTemplateError(f"{goal_type}.steps must be a list")
        for step_index, step in enumerate(steps):
            _validate_step(goal_type, step_index, step)
        templates[goal_type] = template
    return templates


def _validate_step(goal_type: str, step_index: int, step: Any) -> None:
    if not isinstance(step, dict):
        raise GoalTemplateError(f"{goal_type}.steps[{step_index}] must be an object")
    step_type = step.get("goal_type")
    if not isinstance(step_type, str) or not step_type:
        raise GoalTemplateError(f"{goal_type}.steps[{step_index}].goal_type is required")
    payload = step.get("payload", {})
    if not isinstance(payload, dict):
        raise GoalTemplateError(f"{goal_type}.steps[{step_index}].payload must be an object")
    when = step.get("when")
    if when is not None and not isinstance(when, (str, list)):
        raise GoalTemplateError(f"{goal_type}.steps[{step_index}].when is invalid")
    if isinstance(when, list) and not all(isinstance(item, str) for item in when):
        raise GoalTemplateError(f"{goal_type}.steps[{step_index}].when must contain strings")
    conditions = [when] if isinstance(when, str) else when or []
    unknown = [condition for condition in conditions if condition not in ALLOWED_CONDITIONS]
    if unknown:
        raise GoalTemplateError(
            f"{goal_type}.steps[{step_index}].when contains unknown condition: {unknown[0]}"
        )


def _context_for(
    state: RegionState,
    entity: dict[str, Any],
    goal: dict[str, Any],
) -> dict[str, Any]:
    payload = goal.get("payload") or {}
    tournament_id = payload.get("tournament_id")
    tournament = None
    if tournament_id is not None:
        tournament = state.tournaments_by_id.get(int(tournament_id))

    target_region_id = (
        payload.get("region_id")
        or payload.get("target_region_id")
        or (tournament or {}).get("region_id")
    )
    starts_at = payload.get("starts_at_game_tick") or (tournament or {}).get(
        "starts_at_game_tick"
    )
    registration_tick = (
        payload.get("registration_opens_at_game_tick")
        or (tournament or {}).get("registration_opens_at_game_tick")
        or starts_at
    )
    return {
        "entity": entity,
        "goal": goal,
        "payload": payload,
        "tournament": tournament,
        "tournament_id": tournament_id,
        "faction_id": payload.get("faction_id"),
        "region_id": payload.get("region_id"),
        "target_region_id": target_region_id,
        "registration_tick": registration_tick,
        "starts_at": starts_at,
    }


def _requirements_met(template: dict[str, Any], context: dict[str, Any]) -> bool:
    requirements = template.get("requires", [])
    if isinstance(requirements, str):
        requirements = [requirements]
    return all(_lookup_ref(f"${name}", context) is not MISSING for name in requirements)


def _conditions_match(conditions: Any, context: dict[str, Any]) -> bool:
    if conditions is None:
        return True
    if isinstance(conditions, str):
        conditions = [conditions]
    return all(_condition_matches(condition, context) for condition in conditions)


def _condition_matches(condition: str, context: dict[str, Any]) -> bool:
    if condition == "target_region_exists":
        return context["target_region_id"] is not None
    if condition == "entity_not_in_target_region":
        target_region_id = context["target_region_id"]
        return target_region_id is not None and int(
            context["entity"].get("region_id") or 0
        ) != int(target_region_id)
    if condition == "registration_tick_exists":
        return context["registration_tick"] is not None
    if condition == "starts_at_exists":
        return context["starts_at"] is not None
    raise GoalTemplateError(f"unknown goal template condition: {condition}")


def _resolve_payload(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if "ref" in value:
            resolved = _lookup_ref(str(value["ref"]), context)
            if resolved is MISSING:
                default = value.get("default", MISSING)
                return MISSING if default is MISSING else copy.deepcopy(default)
            return copy.deepcopy(resolved)
        out: dict[str, Any] = {}
        for key, nested_value in value.items():
            resolved = _resolve_payload(nested_value, context)
            if resolved is not MISSING:
                out[key] = resolved
        return out
    if isinstance(value, list):
        return [
            resolved
            for item in value
            if (resolved := _resolve_payload(item, context)) is not MISSING
        ]
    if isinstance(value, str) and value.startswith("$"):
        resolved = _lookup_ref(value, context)
        return MISSING if resolved is MISSING else copy.deepcopy(resolved)
    return copy.deepcopy(value)


def _lookup_ref(ref: str, context: dict[str, Any]) -> Any:
    path = ref[1:] if ref.startswith("$") else ref
    if not path:
        return MISSING
    parts = path.split(".")
    current: Any = context.get(parts[0], MISSING)
    for part in parts[1:]:
        if current is MISSING:
            return MISSING
        if not isinstance(current, dict):
            return MISSING
        current = current.get(part, MISSING)
    return current


def _has_incomplete_children(
    goals: list[dict[str, Any]],
    parent: dict[str, Any],
) -> bool:
    parent_id = parent.get("id")
    return any(
        child.get("parent_goal_id") == parent_id
        for child in goals
        if child.get("status") not in TERMINAL_STATUSES
    )


def _child_goal(
    parent: dict[str, Any],
    goal_type: str,
    order: int,
    payload: dict[str, Any],
    *,
    completion_mode: str,
) -> dict[str, Any]:
    return {
        "id": None,
        "entity_id": int(parent["entity_id"]),
        "parent_goal_id": int(parent["id"]),
        "goal_type": goal_type,
        "status": "pending",
        "priority": int(parent.get("priority", 3)),
        "urgency": int(parent.get("urgency", 0)),
        "deadline_game_tick": parent.get("deadline_game_tick"),
        "interruptible": bool(parent.get("interruptible", True)),
        "completion_mode": completion_mode,
        "active": False,
        "progress": 0,
        "cost": parent.get("cost", 0),
        "danger": parent.get("danger", 0),
        "payload": {"order": order, **payload},
        "started_at_game_tick": None,
        "paused_at_game_tick": None,
        "completed_at_game_tick": None,
    }

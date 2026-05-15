"""Persistent goal selection and shallow execution."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..goal_templates import expand_goal_template
from ..state import PendingEvent, RegionState, TickContext

ACTIVE_STATUSES = {"pending", "active", "paused"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
MAX_ZERO_DURATION_TRAVEL_HOPS = 32


def goal_score(goal: dict[str, Any], ctx: TickContext) -> float:
    """Dynamic score used by the per-entity scheduler."""
    score = float(goal.get("priority", 3)) + float(goal.get("urgency", 0))
    deadline = goal.get("deadline_game_tick")
    if deadline is not None:
        ticks_until = int(deadline) - ctx.absolute_game_tick
        score += 50.0 if ticks_until <= 0 else max(0.0, 20.0 - (ticks_until / 10.0))
    score -= float(goal.get("cost", 0))
    score -= float(goal.get("danger", 0))
    return score


def goal_brain(state: RegionState, ctx: TickContext) -> list[PendingEvent]:
    """Choose and advance one active goal per entity."""
    events: list[PendingEvent] = []
    for entity in state.entities:
        entity_id = int(entity["id"])
        goals = state.goals_by_entity_id.get(entity_id, [])
        if not goals:
            continue

        _ensure_template_subgoals(state, entity, goals)
        chosen = _choose_goal(goals, ctx)
        current = _active_goal(goals)
        if chosen is None:
            continue

        if current is not chosen:
            if current is not None:
                _pause_goal(state, current, ctx, events)
            _activate_goal(state, chosen, ctx, events)

        events.extend(_execute_goal(state, entity, chosen, ctx))

    return events


def _choose_goal(goals: list[dict[str, Any]], ctx: TickContext) -> dict[str, Any] | None:
    current = _active_goal(goals)
    if current is not None and not bool(current.get("interruptible", True)):
        return current

    candidates = _candidate_goals(goals)
    if not candidates:
        return current
    return max(candidates, key=lambda goal: (goal_score(goal, ctx), -_goal_order(goal)))


def _candidate_goals(goals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    children_by_parent = _children_by_parent(goals)
    candidates: list[dict[str, Any]] = []
    for goal in goals:
        if goal.get("status") not in ACTIVE_STATUSES:
            continue
        goal_id = goal.get("id")
        if goal_id is not None and _incomplete_children(children_by_parent, int(goal_id)):
            continue
        if _child_is_allowed(goal, goals, children_by_parent):
            candidates.append(goal)
    return candidates


def _child_is_allowed(
    goal: dict[str, Any],
    goals: list[dict[str, Any]],
    children_by_parent: dict[int, list[dict[str, Any]]],
) -> bool:
    parent_id = goal.get("parent_goal_id")
    if parent_id is None:
        return True

    parent = next((g for g in goals if g.get("id") == parent_id), None)
    if parent is None:
        return True
    siblings = _incomplete_children(children_by_parent, int(parent_id))
    mode = str(parent.get("completion_mode", "ordered"))
    if mode == "ordered":
        return siblings and siblings[0] is goal
    return goal in siblings


def _active_goal(goals: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            goal
            for goal in goals
            if bool(goal.get("active")) and goal.get("status") == "active"
        ),
        None,
    )


def _activate_goal(
    state: RegionState,
    goal: dict[str, Any],
    ctx: TickContext,
    events: list[PendingEvent],
) -> None:
    goal["active"] = True
    goal["status"] = "active"
    goal["paused_at_game_tick"] = None
    if goal.get("started_at_game_tick") is None:
        goal["started_at_game_tick"] = ctx.absolute_game_tick
    state.mark_goal_dirty(goal.get("id"))
    events.append(_event("goal.activated", goal, ctx, score=goal_score(goal, ctx)))


def _pause_goal(
    state: RegionState,
    goal: dict[str, Any],
    ctx: TickContext,
    events: list[PendingEvent],
) -> None:
    goal["active"] = False
    if goal.get("status") not in TERMINAL_STATUSES:
        goal["status"] = "paused" if bool(goal.get("interruptible", True)) else "active"
        goal["paused_at_game_tick"] = ctx.absolute_game_tick
    state.mark_goal_dirty(goal.get("id"))
    events.append(_event("goal.paused", goal, ctx))


def _complete_goal(
    state: RegionState,
    goal: dict[str, Any],
    ctx: TickContext,
    events: list[PendingEvent],
    *,
    result: dict[str, Any] | None = None,
) -> None:
    goal["active"] = False
    goal["status"] = "completed"
    goal["progress"] = 100
    goal["completed_at_game_tick"] = ctx.absolute_game_tick
    state.mark_goal_dirty(goal.get("id"))
    events.append(_event("goal.completed", goal, ctx, result=result))


def _fail_goal(
    state: RegionState,
    goal: dict[str, Any],
    ctx: TickContext,
    events: list[PendingEvent],
    *,
    reason: str,
    extra: dict[str, Any] | None = None,
) -> None:
    goal["active"] = False
    goal["status"] = "failed"
    goal["completed_at_game_tick"] = ctx.absolute_game_tick
    state.mark_goal_dirty(goal.get("id"))
    result = {"reason": reason, **(extra or {})}
    events.append(_event("goal.failed", goal, ctx, result=result))


def _execute_goal(
    state: RegionState,
    entity: dict[str, Any],
    goal: dict[str, Any],
    ctx: TickContext,
) -> list[PendingEvent]:
    events: list[PendingEvent] = []
    goal_type = str(goal.get("goal_type"))
    if goal_type == "wait":
        _advance_timed_goal(state, goal, ctx, events)
    elif goal_type == "wait_until":
        _advance_wait_until(state, goal, ctx, events)
    elif goal_type == "travel_segment":
        completed = _execute_travel_segment(state, entity, goal, ctx, events)
        if completed:
            _drain_zero_duration_travel_segments(state, entity, goal, ctx, events)
    elif goal_type == "travel_to_region":
        payload = goal.get("payload") or {}
        target_region_id = payload.get("region_id") or payload.get("target_region_id")

        parent_gid = goal.get("id")
        segment_children = [
            g
            for g in state.goals_by_entity_id.get(int(entity["id"]), [])
            if g.get("parent_goal_id") == parent_gid and g.get("goal_type") == "travel_segment"
        ]

        if segment_children:
            if target_region_id is not None and int(entity.get("region_id") or 0) == int(
                target_region_id
            ):
                _complete_goal(
                    state,
                    goal,
                    ctx,
                    events,
                    result={"region_id": int(target_region_id)},
                )
            return events

        if target_region_id is not None and int(entity.get("region_id") or 0) == int(
            target_region_id
        ):
            _complete_goal(
                state,
                goal,
                ctx,
                events,
                result={"region_id": int(target_region_id)},
            )
            return events

        if target_region_id is None:
            _fail_goal(
                state,
                goal,
                ctx,
                events,
                reason="missing_target_region",
            )
            return events

        if goal.get("id") is None and goal.get("parent_goal_id") is not None:
            return events

        if "duration_ticks" not in payload:
            _fail_goal(
                state,
                goal,
                ctx,
                events,
                reason="no_route_no_duration",
            )
            return events

        completed = _advance_timed_goal(state, goal, ctx, events, emit_complete=False)
        if completed:
            target_region_id_int = int(target_region_id)
            target_region = state.regions_by_id.get(target_region_id_int)
            entity["region_id"] = target_region_id_int
            entity["zone"] = (
                str(target_region["name"])
                if target_region is not None
                else f"Region {target_region_id_int}"
            )
            state.mark_entity_dirty(int(entity["id"]))
            _complete_goal(
                state,
                goal,
                ctx,
                events,
                result={"region_id": target_region_id},
            )
    elif goal_type == "join_faction":
        payload = goal.get("payload") or {}
        _complete_goal(
            state,
            goal,
            ctx,
            events,
            result={"faction_id": payload.get("faction_id"), "ready": True},
        )
    elif goal_type == "register_for_tournament":
        _register_for_tournament(state, goal, ctx, events)
    elif goal_type == "compete_in_tournament":
        _sync_compete_goal_with_tournament(state, goal, ctx, events)
    return events


def _advance_timed_goal(
    state: RegionState,
    goal: dict[str, Any],
    ctx: TickContext,
    events: list[PendingEvent],
    *,
    emit_complete: bool = True,
) -> bool:
    duration = _duration_ticks(goal)
    started = goal.get("started_at_game_tick")
    started_tick = int(started) if started is not None else ctx.absolute_game_tick
    elapsed = max(1, ctx.absolute_game_tick - started_tick + 1)
    goal["progress"] = 100.0 if duration == 0 else min(100.0, (elapsed / duration) * 100.0)
    state.mark_goal_dirty(goal.get("id"))
    if float(goal["progress"]) < 100.0:
        return False
    if emit_complete:
        _complete_goal(state, goal, ctx, events)
    return True


def _duration_ticks(goal: dict[str, Any]) -> int:
    payload = goal.get("payload") or {}
    return max(0, int(payload.get("duration_ticks", 1)))


def _execute_travel_segment(
    state: RegionState,
    entity: dict[str, Any],
    goal: dict[str, Any],
    ctx: TickContext,
    events: list[PendingEvent],
) -> bool:
    completed = _advance_timed_goal(state, goal, ctx, events, emit_complete=False)
    if not completed:
        return False

    payload = goal.get("payload") or {}
    to_id = payload.get("to_region_id")
    if to_id is not None:
        to_int = int(to_id)
        target_region = state.regions_by_id.get(to_int)
        to_name = payload.get("to_name")
        entity["region_id"] = to_int
        entity["zone"] = (
            str(to_name)
            if isinstance(to_name, str) and to_name
            else (
                str(target_region["name"])
                if target_region is not None
                else f"Region {to_int}"
            )
        )
        state.mark_entity_dirty(int(entity["id"]))
    _complete_goal(
        state,
        goal,
        ctx,
        events,
        result={"to_region_id": to_id},
    )
    return True


def _drain_zero_duration_travel_segments(
    state: RegionState,
    entity: dict[str, Any],
    completed_segment: dict[str, Any],
    ctx: TickContext,
    events: list[PendingEvent],
) -> None:
    current = completed_segment
    for _ in range(MAX_ZERO_DURATION_TRAVEL_HOPS):
        next_segment = _next_zero_duration_travel_segment(state, entity, current)
        if next_segment is None:
            return
        if not bool(next_segment.get("active")):
            _activate_goal(state, next_segment, ctx, events)
        if not _execute_travel_segment(state, entity, next_segment, ctx, events):
            return
        current = next_segment
    events.append(_event("goal.zero_duration_travel_guard", current, ctx))


def _next_zero_duration_travel_segment(
    state: RegionState,
    entity: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any] | None:
    parent_id = current.get("parent_goal_id")
    if parent_id is None:
        return None

    goals = state.goals_by_entity_id.get(int(entity["id"]), [])
    parent = next((g for g in goals if g.get("id") == parent_id), None)
    if parent is None or str(parent.get("completion_mode", "ordered")) != "ordered":
        return None

    children = _children_by_parent(goals).get(int(parent_id), [])
    for child in children:
        if child.get("status") in TERMINAL_STATUSES:
            continue
        if child.get("goal_type") != "travel_segment":
            return None
        if _duration_ticks(child) != 0:
            return None
        return child
    return None


def _advance_wait_until(
    state: RegionState,
    goal: dict[str, Any],
    ctx: TickContext,
    events: list[PendingEvent],
) -> None:
    payload = goal.get("payload") or {}
    target_tick = payload.get("target_game_tick")
    if target_tick is None:
        _complete_goal(state, goal, ctx, events, result={"waited": False})
        return
    target = int(target_tick)
    if ctx.absolute_game_tick >= target:
        goal["progress"] = 100
        _complete_goal(state, goal, ctx, events, result={"target_game_tick": target})
        return
    started = goal.get("started_at_game_tick")
    started_tick = int(started) if started is not None else ctx.absolute_game_tick
    span = max(1, target - started_tick)
    elapsed = max(0, ctx.absolute_game_tick - started_tick)
    goal["progress"] = min(99.0, (elapsed / span) * 100.0)
    state.mark_goal_dirty(goal.get("id"))


def _register_for_tournament(
    state: RegionState,
    goal: dict[str, Any],
    ctx: TickContext,
    events: list[PendingEvent],
) -> None:
    payload = goal.get("payload") or {}
    tournament_id = payload.get("tournament_id")
    if tournament_id is None:
        _complete_goal(state, goal, ctx, events, result={"registered": False})
        return

    tournament_id_int = int(tournament_id)
    entity_id = int(goal["entity_id"])
    participant = _find_tournament_participant(state, tournament_id_int, entity_id)
    if participant is None:
        participant = {
            "tournament_id": tournament_id_int,
            "entity_id": entity_id,
            "status": "registered",
            "seed": payload.get("seed"),
            "eliminated_round": None,
            "joined_at_game_tick": ctx.absolute_game_tick,
            "payload": payload.get("participant_payload") or {},
            "updated_at": None,
        }
        state.add_tournament_participant(participant)
    else:
        participant["status"] = "registered"
        if participant.get("joined_at_game_tick") is None:
            participant["joined_at_game_tick"] = ctx.absolute_game_tick
    state.mark_tournament_participant_dirty(tournament_id_int, entity_id)
    _complete_goal(
        state,
        goal,
        ctx,
        events,
        result={"registered": True, "tournament_id": tournament_id_int},
    )


def _sync_compete_goal_with_tournament(
    state: RegionState,
    goal: dict[str, Any],
    ctx: TickContext,
    events: list[PendingEvent],
) -> None:
    payload = goal.get("payload") or {}
    tournament_id = payload.get("tournament_id")
    if tournament_id is None:
        return
    participant = _find_tournament_participant(
        state,
        int(tournament_id),
        int(goal["entity_id"]),
    )
    if participant is None or participant.get("status") in {"registered", "active"}:
        goal["progress"] = 50
        state.mark_goal_dirty(goal.get("id"))
        return
    _complete_goal(
        state,
        goal,
        ctx,
        events,
        result={
            "tournament_id": int(tournament_id),
            "participant_status": participant.get("status"),
        },
    )


def _ensure_template_subgoals(
    state: RegionState,
    entity: dict[str, Any],
    goals: list[dict[str, Any]],
) -> None:
    for goal in list(goals):
        for child in expand_goal_template(state, entity, goal):
            state.add_goal(child)


def _find_tournament_participant(
    state: RegionState,
    tournament_id: int,
    entity_id: int,
) -> dict[str, Any] | None:
    return next(
        (
            participant
            for participant in state.tournament_participants_by_tournament_id.get(
                int(tournament_id), []
            )
            if int(participant["entity_id"]) == int(entity_id)
        ),
        None,
    )


def _children_by_parent(goals: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for goal in goals:
        parent_id = goal.get("parent_goal_id")
        if parent_id is not None:
            out[int(parent_id)].append(goal)
    for children in out.values():
        children.sort(key=_goal_order)
    return out


def _incomplete_children(
    children_by_parent: dict[int, list[dict[str, Any]]],
    parent_id: int,
) -> list[dict[str, Any]]:
    return [
        child
        for child in children_by_parent.get(parent_id, [])
        if child.get("status") not in TERMINAL_STATUSES
    ]


def _goal_order(goal: dict[str, Any]) -> int:
    payload = goal.get("payload") or {}
    if payload.get("order") is not None:
        return int(payload["order"])
    goal_id = goal.get("id")
    return int(goal_id) if goal_id is not None else 1_000_000


def _event(
    kind: str,
    goal: dict[str, Any],
    ctx: TickContext,
    **extra: Any,
) -> PendingEvent:
    payload = {
        "goal_id": goal.get("id"),
        "goal_type": goal.get("goal_type"),
        "game_tick": ctx.absolute_game_tick,
        **extra,
    }
    return PendingEvent(
        kind=kind,
        significance=2,
        subject_entity_id=int(goal["entity_id"]),
        payload=payload,
    )

"""Faction behavior system: maintain member orders."""

from __future__ import annotations

from typing import Any

from ..state import PendingEvent, RegionState, TickContext

ACTIVE_GOAL_STATUSES = {"pending", "active", "paused"}
TERMINAL_GOAL_STATUSES = {"completed", "failed", "cancelled"}


def rank_bucket(rank: object) -> str:
    """Bucket a raw rank string into a small behavior-relevant category."""
    r = str(rank or "").strip().lower()
    if not r:
        return "member"
    if r in {"patriarch", "matriarch", "lord", "lady", "master", "archmage"}:
        return "leader"
    if r == "heir":
        return "heir"
    if r in {"champion", "knight", "officer", "elite"}:
        return "elite"
    if r in {"councilor", "advisor", "minister"}:
        return "council"
    # Common "regular member" labels.
    if r in {"member", "scion", "student"}:
        return "member"
    return "member"


def faction_behavior(state: RegionState, ctx: TickContext) -> list[PendingEvent]:
    events: list[PendingEvent] = []
    _sync_order_statuses(state, ctx)
    return events


def _controller_faction_id(controls: list[dict[str, Any]]) -> int | None:
    controller = next((c for c in controls if c.get("role") == "controller"), None)
    owner = next((c for c in controls if c.get("role") == "owner"), None)
    row = controller or owner
    return int(row["faction_id"]) if row and row.get("faction_id") is not None else None


def _has_active_order(state: RegionState, faction_id: int, order_type: str, region_id: int) -> bool:
    for o in state.faction_orders:
        if o.get("status") != "active":
            continue
        if int(o.get("faction_id") or 0) != int(faction_id):
            continue
        if str(o.get("order_type") or "") != order_type:
            continue
        if int(o.get("region_id") or 0) != int(region_id):
            continue
        return True
    return False


def _sync_order_statuses(state: RegionState, ctx: TickContext) -> None:
    goals_by_source_key = _faction_goal_terminal_statuses(state)
    if not goals_by_source_key:
        return

    for order in state.faction_orders:
        if order.get("status") != "active":
            continue
        payload = order.get("payload") or {}
        source_key = payload.get("source_key") if isinstance(payload, dict) else None
        if not source_key:
            continue
        goal = goals_by_source_key.get(str(source_key))
        if goal is None:
            continue

        order["status"] = str(goal["status"])
        order["completed_at_game_tick"] = (
            goal.get("completed_at_game_tick") or ctx.absolute_game_tick
        )
        state.mark_faction_order_dirty(order.get("id"))


def _faction_goal_terminal_statuses(state: RegionState) -> dict[str, dict[str, Any]]:
    by_source_key: dict[str, dict[str, Any]] = {}
    for goal in state.goals:
        status = str(goal.get("status") or "")
        if status not in TERMINAL_GOAL_STATUSES:
            continue
        payload = goal.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if payload.get("source_type") != "faction_order":
            continue
        source_key = payload.get("source_key")
        if not source_key:
            continue
        by_source_key[str(source_key)] = goal
    return by_source_key


def _member_has_conflicting_goal(state: RegionState, entity_id: int) -> bool:
    for goal in state.goals_by_entity_id.get(int(entity_id), []):
        if goal.get("status") not in ACTIVE_GOAL_STATUSES:
            continue
        if not bool(goal.get("interruptible", True)):
            return True
        if bool(goal.get("active")) and goal.get("status") == "active":
            return True
    return False


def _pick_member_for_faction(
    state: RegionState,
    faction_id: int,
    *,
    prefer: set[str],
) -> dict[str, Any] | None:
    members = state.members_by_faction_id.get(int(faction_id), [])
    candidates = [
        member
        for member in members
        if not _member_has_conflicting_goal(state, int(member["entity_id"]))
    ]
    if not candidates:
        return None

    def score(m: dict[str, Any]) -> tuple[int, int]:
        bucket = rank_bucket(m.get("rank"))
        preferred = 1 if bucket in prefer else 0
        return (preferred, -int(m.get("entity_id") or 0))

    # Pick deterministically: preferred bucket, then lowest entity id.
    best = max(candidates, key=score)
    return best


def _issue_order_and_goal(
    state: RegionState,
    *,
    faction_id: int,
    entity_id: int,
    target_region_id: int,
    order_type: str,
    rank: str,
    source_key: str,
    created_at_game_tick: int,
) -> None:
    bucket = rank_bucket(rank)
    state.add_faction_order(
        {
            "id": None,
            "faction_id": int(faction_id),
            "entity_id": int(entity_id),
            "region_id": int(target_region_id),
            "order_type": order_type,
            "status": "active",
            "payload": {
                "rank": rank,
                "rank_bucket": bucket,
                "target_region_id": int(target_region_id),
                "source_key": source_key,
            },
            "created_at_game_tick": int(created_at_game_tick),
            "completed_at_game_tick": None,
        }
    )

    # Issue an entity travel goal. Keep it low priority; let entity goal brain arbitrate.
    state.add_goal(
        {
            "id": None,
            "entity_id": int(entity_id),
            "parent_goal_id": None,
            "goal_type": "travel_to_region",
            "status": "pending",
            "priority": 3,
            "urgency": 0,
            "deadline_game_tick": None,
            "interruptible": True,
            "completion_mode": "ordered",
            "active": False,
            "progress": 0,
            "cost": 0,
            "danger": 0,
            "payload": {
                "region_id": int(target_region_id),
                "source_type": "faction_order",
                "source_key": source_key,
                "faction_id": int(faction_id),
                "order_type": order_type,
            },
            "created_at": None,
            "updated_at": None,
            "started_at_game_tick": None,
            "paused_at_game_tick": None,
            "completed_at_game_tick": None,
        }
    )


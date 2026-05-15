from __future__ import annotations

import random
from datetime import datetime, timezone

from rts_world.sim.state import RegionState, TickContext
from rts_world.sim.systems.factions import (
    _pick_member_for_faction,
    faction_behavior,
    rank_bucket,
)


def _ctx(game_tick: int = 10) -> TickContext:
    return TickContext(
        region_id=1,
        now=datetime.now(timezone.utc),
        game_day=0,
        game_tick=game_tick,
        rng=random.Random(1),
    )


def test_rank_bucket_basic_mappings() -> None:
    assert rank_bucket("patriarch") == "leader"
    assert rank_bucket("heir") == "heir"
    assert rank_bucket("knight") == "elite"
    assert rank_bucket("councilor") == "council"
    assert rank_bucket("scion") == "member"
    assert rank_bucket("") == "member"


def test_faction_behavior_does_not_issue_patrol_orders_for_now() -> None:
    state = RegionState(
        region={"id": 1, "name": "Root"},
        regions_by_id={
            1: {"id": 1, "name": "Root", "type": "region", "parent_id": None},
            2: {"id": 2, "name": "Border", "type": "border", "parent_id": 1},
        },
        entities=[
            {"id": 1, "name": "Ada", "type": "humanoid", "zone": "Root", "region_id": 1},
        ],
        entities_by_id={
            1: {"id": 1, "name": "Ada", "type": "humanoid", "zone": "Root", "region_id": 1},
        },
    )
    # Controller faction owns the border.
    state.add_region_control({"region_id": 2, "role": "controller", "faction_id": 10})
    # Faction member is in the root region, not in the border.
    state.add_member({"entity_id": 1, "faction_id": 10, "rank": "member", "source": "faction"})

    events = faction_behavior(state, _ctx(game_tick=5))

    assert events == []
    assert state.faction_orders == []
    assert state.goals == []


def test_faction_behavior_completes_order_when_linked_goal_completes() -> None:
    state = RegionState(region={"id": 1, "name": "Root"})
    source_key = "faction_order:10:station_at_region:1:2:5"
    state.add_faction_order(
        {
            "id": 123,
            "faction_id": 10,
            "entity_id": 1,
            "region_id": 2,
            "order_type": "station_at_region",
            "status": "active",
            "payload": {"source_key": source_key},
            "created_at_game_tick": 1,
            "completed_at_game_tick": None,
            "created_at": None,
            "updated_at": None,
        }
    )
    state.add_goal(
        {
            "id": 456,
            "entity_id": 1,
            "parent_goal_id": None,
            "goal_type": "travel_to_region",
            "status": "completed",
            "priority": 3,
            "urgency": 0,
            "deadline_game_tick": None,
            "interruptible": True,
            "completion_mode": "ordered",
            "active": False,
            "progress": 100,
            "cost": 0,
            "danger": 0,
            "payload": {
                "source_type": "faction_order",
                "source_key": source_key,
            },
            "created_at": None,
            "updated_at": None,
            "started_at_game_tick": 2,
            "paused_at_game_tick": None,
            "completed_at_game_tick": 9,
        }
    )

    faction_behavior(state, _ctx(game_tick=5))

    order = state.faction_orders[0]
    assert order["status"] == "completed"
    assert order["completed_at_game_tick"] == 9
    assert state.dirty_faction_order_ids == {123}


def test_member_picker_skips_members_with_conflicting_active_goals() -> None:
    state = RegionState(region={"id": 1, "name": "Root"})
    state.add_member({"entity_id": 1, "faction_id": 10, "rank": "knight", "source": "faction"})
    state.add_member({"entity_id": 2, "faction_id": 10, "rank": "member", "source": "faction"})
    state.add_goal(
        {
            "id": 1,
            "entity_id": 1,
            "parent_goal_id": None,
            "goal_type": "wait",
            "status": "active",
            "priority": 3,
            "urgency": 0,
            "deadline_game_tick": None,
            "interruptible": False,
            "completion_mode": "ordered",
            "active": True,
            "progress": 0,
            "cost": 0,
            "danger": 0,
            "payload": {},
            "created_at": None,
            "updated_at": None,
            "started_at_game_tick": 1,
            "paused_at_game_tick": None,
            "completed_at_game_tick": None,
        }
    )

    picked = _pick_member_for_faction(state, 10, prefer={"member", "elite"})

    assert picked is not None
    assert picked["entity_id"] == 2


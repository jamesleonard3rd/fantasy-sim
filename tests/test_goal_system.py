from __future__ import annotations

import random
from datetime import datetime, timezone

import pytest

from rts_world.sim.goal_templates import GoalTemplateError, validate_goal_template_data
from rts_world.sim.state import RegionState, TickContext
from rts_world.sim.systems.goals import goal_brain, goal_score


def _ctx(game_tick: int = 10) -> TickContext:
    return TickContext(
        region_id=1,
        now=datetime.now(timezone.utc),
        game_day=0,
        game_tick=game_tick,
        rng=random.Random(1),
    )


def _goal(
    goal_id: int,
    entity_id: int,
    goal_type: str,
    *,
    status: str = "pending",
    priority: int = 3,
    urgency: int = 0,
    active: bool = False,
    interruptible: bool = True,
    parent_goal_id: int | None = None,
    payload: dict | None = None,
) -> dict[str, object]:
    return {
        "id": goal_id,
        "entity_id": entity_id,
        "parent_goal_id": parent_goal_id,
        "goal_type": goal_type,
        "status": status,
        "priority": priority,
        "urgency": urgency,
        "deadline_game_tick": None,
        "interruptible": interruptible,
        "completion_mode": "ordered",
        "active": active,
        "progress": 0,
        "cost": 0,
        "danger": 0,
        "payload": payload or {},
        "started_at_game_tick": None,
        "paused_at_game_tick": None,
        "completed_at_game_tick": None,
    }


def _state(goals: list[dict[str, object]]) -> RegionState:
    state = RegionState(
        region={"id": 1, "name": "Test"},
        regions_by_id={
            1: {"id": 1, "name": "Test"},
            2: {"id": 2, "name": "Frostpine Reach"},
        },
        entities=[
            {
                "id": 1,
                "name": "Ada",
                "type": "humanoid",
                "race_id": 1,
                "subrace_id": None,
                "created_at": None,
                "zone": "Test",
                "region_id": 1,
            }
        ],
    )
    for goal in goals:
        state.add_goal(goal)
    return state


def test_goal_score_includes_deadline_pressure_and_costs() -> None:
    urgent = _goal(1, 1, "wait", priority=3, urgency=5)
    urgent["deadline_game_tick"] = 12
    risky = _goal(2, 1, "wait", priority=5, urgency=5)
    risky["danger"] = 20

    assert goal_score(urgent, _ctx(game_tick=10)) > goal_score(risky, _ctx(game_tick=10))


def test_higher_scored_goal_interrupts_active_goal() -> None:
    resting = _goal(1, 1, "wait", status="active", active=True, payload={"duration_ticks": 5})
    fleeing = _goal(2, 1, "wait", priority=5, urgency=50)
    state = _state([resting, fleeing])

    events = goal_brain(state, _ctx())

    assert resting["status"] == "paused"
    assert resting["active"] is False
    assert fleeing["status"] == "completed"
    assert fleeing["active"] is False
    assert state.dirty_goal_ids == {1, 2}
    assert [event.kind for event in events] == [
        "goal.paused",
        "goal.activated",
        "goal.completed",
    ]


def test_non_interruptible_goal_remains_active() -> None:
    training = _goal(
        1,
        1,
        "wait",
        status="active",
        active=True,
        interruptible=False,
        payload={"duration_ticks": 5},
    )
    emergency = _goal(2, 1, "wait", priority=5, urgency=100)
    state = _state([training, emergency])

    goal_brain(state, _ctx())

    assert training["status"] == "active"
    assert training["active"] is True
    assert emergency["status"] == "pending"


def test_join_faction_decomposes_into_travel_subgoal() -> None:
    join = _goal(
        1,
        1,
        "join_faction",
        priority=4,
        payload={"faction_id": 7, "region_id": 2, "travel_ticks": 3},
    )
    state = _state([join])

    events = goal_brain(state, _ctx())

    assert join["active"] is False
    assert join["status"] == "pending"
    child = next(goal for goal in state.goals if goal.get("id") is None)
    assert child["goal_type"] == "travel_to_region"
    assert child["parent_goal_id"] == 1
    assert child["status"] == "active"
    assert child["progress"] < 100
    assert [event.kind for event in events] == ["goal.activated"]


def test_template_travel_without_override_waits_to_route_after_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rts_world.sim import travel as travel_mod

    def fake_route(
        start_region_id: int | None,
        end_region_id: int,
        regions_by_id: dict[int, dict[str, object]],
    ) -> list[travel_mod.TravelSegment]:
        assert start_region_id == 1
        assert end_region_id == 2
        assert regions_by_id
        return [travel_mod.TravelSegment(1, 2, "Test", "Frostpine Reach", 2, "road")]

    monkeypatch.setattr(travel_mod, "route_travel_segments", fake_route)
    join = _goal(1, 1, "join_faction", payload={"faction_id": 7, "region_id": 2})
    state = _state([join])

    first_events = goal_brain(state, _ctx(game_tick=10))
    travel = next(goal for goal in state.goals if goal.get("parent_goal_id") == 1)

    assert travel["goal_type"] == "travel_to_region"
    assert travel["id"] is None
    assert travel["status"] == "active"
    assert travel["progress"] == 0
    assert state.entities[0]["region_id"] == 1
    assert [event.kind for event in first_events] == ["goal.activated"]

    # Once the generated travel goal has a database id, it can become a segment parent.
    travel["id"] = 20
    second_events = goal_brain(state, _ctx(game_tick=11))
    segments = [goal for goal in state.goals if goal.get("parent_goal_id") == 20]

    assert [segment["goal_type"] for segment in segments] == ["travel_segment"]
    assert segments[0]["status"] == "active"
    assert travel["status"] == "paused"
    assert [event.kind for event in second_events] == ["goal.paused", "goal.activated"]


def test_travel_to_region_can_run_as_direct_goal() -> None:
    travel = _goal(
        1,
        1,
        "travel_to_region",
        payload={"region_id": 2, "duration_ticks": 1, "zone": "Ignored Zone"},
    )
    state = _state([travel])

    events = goal_brain(state, _ctx())

    assert travel["status"] == "completed"
    assert state.entities[0]["region_id"] == 2
    assert state.entities[0]["zone"] == "Frostpine Reach"
    assert state.dirty_entity_ids == {1}
    assert [event.kind for event in events] == ["goal.activated", "goal.completed"]


def test_explicit_travel_duration_keeps_direct_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rts_world.sim import travel as travel_mod

    def unexpected_route(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("duration_ticks travel should not route through travel_edges")

    monkeypatch.setattr(travel_mod, "route_travel_segments", unexpected_route)

    travel = _goal(1, 1, "travel_to_region", payload={"region_id": 2, "duration_ticks": 1})
    state = _state([travel])

    events = goal_brain(state, _ctx())

    assert travel["status"] == "completed"
    assert state.entities[0]["region_id"] == 2
    assert [event.kind for event in events] == ["goal.activated", "goal.completed"]


def test_enter_tournament_decomposes_into_ordered_children() -> None:
    enter = _goal(
        1,
        1,
        "enter_tournament",
        priority=4,
        payload={
            "tournament_id": 5,
            "region_id": 2,
            "registration_opens_at_game_tick": 20,
            "starts_at_game_tick": 30,
            "travel_ticks": 2,
            "seed": 1,
        },
    )
    state = _state([enter])

    goal_brain(state, _ctx(game_tick=10))

    children = [goal for goal in state.goals if goal.get("parent_goal_id") == 1]
    assert [child["goal_type"] for child in children] == [
        "travel_to_region",
        "wait_until",
        "register_for_tournament",
        "wait_until",
        "compete_in_tournament",
    ]
    assert children[0]["status"] == "active"
    assert [child["payload"]["order"] for child in children] == [1, 2, 3, 4, 5]


def test_register_for_tournament_goal_adds_participant() -> None:
    register = _goal(
        1,
        1,
        "register_for_tournament",
        payload={"tournament_id": 5, "seed": 2},
    )
    state = _state([register])

    events = goal_brain(state, _ctx())

    assert register["status"] == "completed"
    assert state.tournament_participants[0]["tournament_id"] == 5
    assert state.tournament_participants[0]["entity_id"] == 1
    assert state.tournament_participants[0]["status"] == "registered"
    assert state.dirty_tournament_participant_keys == {(5, 1)}
    assert [event.kind for event in events] == ["goal.activated", "goal.completed"]


def test_goal_template_validation_rejects_bad_step() -> None:
    with pytest.raises(GoalTemplateError, match="goal_type is required"):
        validate_goal_template_data(
            {
                "goal_templates": [
                    {
                        "goal_type": "bad_parent",
                        "steps": [
                            {
                                "payload": {},
                            }
                        ],
                    }
                ]
            }
        )


def test_travel_to_region_expands_route_into_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rts_world.sim import travel as travel_mod

    def fake_route(
        start_region_id: int | None,
        end_region_id: int,
        regions_by_id: dict[str, object],
    ) -> list[travel_mod.TravelSegment]:
        assert start_region_id == 1
        assert end_region_id == 3
        assert regions_by_id
        return [
            travel_mod.TravelSegment(1, 2, "A", "B", 2, "road"),
            travel_mod.TravelSegment(2, 3, "B", "C", 3, "road"),
        ]

    monkeypatch.setattr(travel_mod, "route_travel_segments", fake_route)

    travel = _goal(10, 1, "travel_to_region", payload={"region_id": 3})
    state = RegionState(
        region={"id": 1, "name": "A"},
        regions_by_id={
            1: {"id": 1, "name": "A"},
            2: {"id": 2, "name": "B"},
            3: {"id": 3, "name": "C"},
        },
        entities=[
            {
                "id": 1,
                "name": "Ada",
                "type": "humanoid",
                "race_id": 1,
                "subrace_id": None,
                "created_at": None,
                "zone": "A",
                "region_id": 1,
            }
        ],
    )
    state.add_goal(travel)

    events0 = goal_brain(state, _ctx(game_tick=100))
    children = [g for g in state.goals if g.get("parent_goal_id") == 10]
    assert [c["goal_type"] for c in children] == ["travel_segment", "travel_segment"]
    assert children[0]["status"] == "active"
    assert state.entities[0]["region_id"] == 1
    assert [e.kind for e in events0] == ["goal.activated"]

    goal_brain(state, _ctx(game_tick=101))
    assert children[0]["status"] == "completed"
    assert state.entities[0]["region_id"] == 2
    assert children[1]["status"] == "pending"

    goal_brain(state, _ctx(game_tick=102))
    assert children[1]["status"] == "active"

    for tick in (103, 104):
        goal_brain(state, _ctx(game_tick=tick))
    assert children[1]["status"] == "completed"
    assert state.entities[0]["region_id"] == 3

    goal_brain(state, _ctx(game_tick=105))
    assert travel["status"] == "completed"
    assert travel["progress"] == 100


def test_zero_duration_travel_segments_drain_in_same_tick() -> None:
    parent = _goal(10, 1, "travel_to_region", payload={"region_id": 3})
    first = _goal(
        11,
        1,
        "travel_segment",
        parent_goal_id=10,
        payload={
            "order": 1,
            "from_region_id": 1,
            "to_region_id": 2,
            "duration_ticks": 1,
            "from_name": "A",
            "to_name": "Border",
        },
    )
    zero = _goal(
        12,
        1,
        "travel_segment",
        parent_goal_id=10,
        payload={
            "order": 2,
            "from_region_id": 2,
            "to_region_id": 3,
            "duration_ticks": 0,
            "from_name": "Border",
            "to_name": "C",
        },
    )
    state = RegionState(
        region={"id": 1, "name": "A"},
        regions_by_id={
            1: {"id": 1, "name": "A"},
            2: {"id": 2, "name": "Border"},
            3: {"id": 3, "name": "C"},
        },
        entities=[
            {
                "id": 1,
                "name": "Ada",
                "type": "humanoid",
                "race_id": 1,
                "subrace_id": None,
                "created_at": None,
                "zone": "A",
                "region_id": 1,
            }
        ],
    )
    for goal in (parent, first, zero):
        state.add_goal(goal)

    events = goal_brain(state, _ctx(game_tick=100))

    assert first["status"] == "completed"
    assert zero["status"] == "completed"
    assert state.entities[0]["region_id"] == 3
    assert state.entities[0]["zone"] == "C"
    assert [e.kind for e in events] == [
        "goal.activated",
        "goal.completed",
        "goal.activated",
        "goal.completed",
    ]


def test_zero_duration_travel_drain_stops_before_nonzero_segment() -> None:
    parent = _goal(10, 1, "travel_to_region", payload={"region_id": 3})
    first = _goal(
        11,
        1,
        "travel_segment",
        parent_goal_id=10,
        payload={"order": 1, "to_region_id": 2, "duration_ticks": 0},
    )
    second = _goal(
        12,
        1,
        "travel_segment",
        parent_goal_id=10,
        payload={"order": 2, "to_region_id": 3, "duration_ticks": 2},
    )
    state = RegionState(
        region={"id": 1, "name": "A"},
        regions_by_id={
            1: {"id": 1, "name": "A"},
            2: {"id": 2, "name": "Border"},
            3: {"id": 3, "name": "C"},
        },
        entities=[
            {
                "id": 1,
                "name": "Ada",
                "type": "humanoid",
                "race_id": 1,
                "subrace_id": None,
                "created_at": None,
                "zone": "A",
                "region_id": 1,
            }
        ],
    )
    for goal in (parent, first, second):
        state.add_goal(goal)

    goal_brain(state, _ctx(game_tick=100))

    assert first["status"] == "completed"
    assert second["status"] == "pending"
    assert state.entities[0]["region_id"] == 2


def test_travel_no_route_without_duration_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from rts_world.sim import travel as travel_mod

    monkeypatch.setattr(travel_mod, "route_travel_segments", lambda *a, **k: None)

    travel = _goal(11, 1, "travel_to_region", payload={"region_id": 2})
    state = RegionState(
        region={"id": 1, "name": "Test"},
        regions_by_id={
            1: {"id": 1, "name": "Test"},
            2: {"id": 2, "name": "Frostpine Reach"},
        },
        entities=[
            {
                "id": 1,
                "name": "Ada",
                "type": "humanoid",
                "race_id": 1,
                "subrace_id": None,
                "created_at": None,
                "zone": "Test",
                "region_id": 1,
            }
        ],
    )
    state.add_goal(travel)

    events = goal_brain(state, _ctx(game_tick=1))
    assert travel["status"] == "failed"
    assert [e.kind for e in events] == ["goal.activated", "goal.failed"]

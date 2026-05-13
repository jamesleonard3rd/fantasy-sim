from __future__ import annotations

import random
from datetime import datetime, timezone

from rts_world.sim.state import RegionState, TickContext
from rts_world.sim.systems.tournaments import tournament_system


def _ctx(game_tick: int = 10) -> TickContext:
    return TickContext(
        region_id=1,
        now=datetime.now(timezone.utc),
        game_day=0,
        game_tick=game_tick,
        rng=random.Random(1),
    )


def _tournament(
    *,
    status: str = "scheduled",
    starts_at: int = 10,
    max_rounds_per_tick: int = 10,
) -> dict[str, object]:
    return {
        "id": 1,
        "region_id": 1,
        "name": "Test Cup",
        "status": status,
        "registration_opens_at_game_tick": 5,
        "registration_closes_at_game_tick": 9,
        "starts_at_game_tick": starts_at,
        "current_round": 0,
        "max_rounds_per_tick": max_rounds_per_tick,
        "winner_entity_id": None,
        "payload": {"min_participants": 2},
        "completed_at_game_tick": None,
    }


def _participant(entity_id: int, seed: int) -> dict[str, object]:
    return {
        "tournament_id": 1,
        "entity_id": entity_id,
        "status": "registered",
        "seed": seed,
        "eliminated_round": None,
        "joined_at_game_tick": 1,
        "payload": {},
    }


def _state(
    tournament: dict[str, object],
    participants: list[dict[str, object]],
) -> RegionState:
    state = RegionState(region={"id": 1, "name": "Arena"})
    state.add_tournament(tournament)
    for participant in participants:
        state.add_tournament_participant(participant)
    return state


def test_tournament_opens_registration_before_start() -> None:
    tournament = _tournament(starts_at=20)
    state = _state(tournament, [])

    events = tournament_system(state, _ctx(game_tick=5))

    assert tournament["status"] == "registration_open"
    assert state.dirty_tournament_ids == {1}
    assert [event.kind for event in events] == ["tournament.registration_opened"]


def test_tournament_runs_all_rounds_and_declares_winner() -> None:
    tournament = _tournament(status="registration_closed")
    participants = [
        _participant(1, 1),
        _participant(2, 4),
        _participant(3, 2),
        _participant(4, 3),
    ]
    state = _state(tournament, participants)

    events = tournament_system(state, _ctx(game_tick=10))

    assert tournament["status"] == "completed"
    assert tournament["winner_entity_id"] == 1
    assert tournament["current_round"] == 2
    statuses = {p["entity_id"]: p["status"] for p in participants}
    assert statuses == {1: "winner", 2: "eliminated", 3: "eliminated", 4: "eliminated"}
    assert "tournament.started" in [event.kind for event in events]
    assert "tournament.winner_declared" in [event.kind for event in events]
    assert state.dirty_tournament_ids == {1}
    assert state.dirty_tournament_participant_keys == {
        (1, 1),
        (1, 2),
        (1, 3),
        (1, 4),
    }


def test_tournament_respects_max_rounds_per_tick() -> None:
    tournament = _tournament(status="registration_closed", max_rounds_per_tick=1)
    participants = [
        _participant(1, 1),
        _participant(2, 4),
        _participant(3, 2),
        _participant(4, 3),
    ]
    state = _state(tournament, participants)

    events = tournament_system(state, _ctx(game_tick=10))

    assert tournament["status"] == "running"
    assert tournament["current_round"] == 1
    assert tournament["payload"]["remaining_entity_ids"] == [1, 4]
    assert [event.kind for event in events].count("tournament.round_completed") == 1

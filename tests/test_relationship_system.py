from __future__ import annotations

import random
from datetime import datetime, timezone

from rts_world.sim.state import RegionState, TickContext
from rts_world.sim.systems.relationships import relationship_dynamics


def _ctx(game_tick: int = 10) -> TickContext:
    return TickContext(
        region_id=1,
        now=datetime.now(timezone.utc),
        game_day=0,
        game_tick=game_tick,
        rng=random.Random(1),
    )


def _term(
    term_id: int,
    subject_id: int,
    target_id: int,
    value: int,
    *,
    source_type: str = "manual",
    source_key: str = "test",
    decay_per_tick: int = 0,
    expires_at_game_tick: int | None = None,
) -> dict[str, object]:
    return {
        "id": term_id,
        "subject_entity_id": subject_id,
        "target_entity_id": target_id,
        "source_type": source_type,
        "source_key": source_key,
        "source_instance": "",
        "value": value,
        "decay_per_tick": decay_per_tick,
        "expires_at_game_tick": expires_at_game_tick,
        "payload": None,
    }


def test_relationship_terms_sum_and_clamp_cached_opinion() -> None:
    state = RegionState(
        region={"id": 1, "name": "Test"},
        relationships=[
            {
                "subject_entity_id": 1,
                "target_entity_id": 2,
                "opinion": 0,
                "last_updated": None,
            }
        ],
        relationship_terms=[
            _term(1, 1, 2, 80, source_key="father"),
            _term(2, 1, 2, 40, source_key="saved_life"),
            _term(3, 1, 2, -5, source_key="argument"),
        ],
    )

    events = relationship_dynamics(state, _ctx())

    assert events == []
    assert state.relationships[0]["opinion"] == 100
    assert state.dirty_relationship_keys == {(1, 2)}


def test_kinship_terms_are_directional() -> None:
    state = RegionState(
        region={"id": 1, "name": "Test"},
        relationships=[
            {"subject_entity_id": 1, "target_entity_id": 2, "opinion": 0},
            {"subject_entity_id": 2, "target_entity_id": 1, "opinion": 0},
        ],
        relationship_terms=[
            _term(1, 1, 2, 50, source_type="kinship", source_key="child"),
            _term(2, 2, 1, 50, source_type="kinship", source_key="father"),
        ],
    )

    relationship_dynamics(state, _ctx())

    opinions = {
        (int(r["subject_entity_id"]), int(r["target_entity_id"])): int(r["opinion"])
        for r in state.relationships
    }
    assert opinions[(1, 2)] == 50
    assert opinions[(2, 1)] == 50
    assert state.dirty_relationship_keys == {(1, 2), (2, 1)}


def test_temporary_terms_decay_toward_zero_before_recalculation() -> None:
    state = RegionState(
        region={"id": 1, "name": "Test"},
        relationships=[
            {"subject_entity_id": 1, "target_entity_id": 2, "opinion": 0},
        ],
        relationship_terms=[
            _term(1, 1, 2, 10, source_key="recent_kindness", decay_per_tick=3),
            _term(2, 1, 2, -6, source_key="recent_insult", decay_per_tick=10),
        ],
    )

    relationship_dynamics(state, _ctx())

    values = {int(t["id"]): int(t["value"]) for t in state.relationship_terms}
    assert values == {1: 7, 2: 0}
    assert state.relationships[0]["opinion"] == 7
    assert state.dirty_relationship_term_ids == {1, 2}
    assert state.dirty_relationship_keys == {(1, 2)}


def test_expired_term_is_zeroed_before_recalculation() -> None:
    state = RegionState(
        region={"id": 1, "name": "Test"},
        relationships=[
            {"subject_entity_id": 1, "target_entity_id": 2, "opinion": 10},
        ],
        relationship_terms=[
            _term(1, 1, 2, 10, source_key="old_memory", expires_at_game_tick=5),
        ],
    )

    relationship_dynamics(state, _ctx(game_tick=10))

    assert state.relationship_terms[0]["value"] == 0
    assert state.relationships[0]["opinion"] == 0
    assert state.dirty_relationship_term_ids == {1}
    assert state.dirty_relationship_keys == {(1, 2)}


def test_expired_term_uses_absolute_game_tick_across_days() -> None:
    state = RegionState(
        region={"id": 1, "name": "Test"},
        relationships=[
            {"subject_entity_id": 1, "target_entity_id": 2, "opinion": 10},
        ],
        relationship_terms=[
            _term(
                1,
                1,
                2,
                10,
                source_key="yesterday_memory",
                expires_at_game_tick=1445,
            ),
        ],
    )

    relationship_dynamics(
        state,
        TickContext(
            region_id=1,
            now=datetime.now(timezone.utc),
            game_day=1,
            game_tick=10,
            rng=random.Random(1),
        ),
    )

    assert state.relationship_terms[0]["value"] == 0
    assert state.relationships[0]["opinion"] == 0
    assert state.dirty_relationship_term_ids == {1}
    assert state.dirty_relationship_keys == {(1, 2)}

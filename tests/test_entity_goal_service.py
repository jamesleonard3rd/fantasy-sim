from __future__ import annotations

import pytest

from rts_world.services import entities as entity_service


def _install_goal_service_fakes(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    inserted: list[dict] = []
    monkeypatch.setattr(entity_service, "_require_entity", lambda conn, entity_id: None)
    monkeypatch.setattr(
        entity_service.entities_repo,
        "entity_goals_table_exists",
        lambda conn: True,
    )
    monkeypatch.setattr(
        entity_service.entities_repo,
        "entity_goal_exists_for_entity",
        lambda conn, entity_id, goal_id: True,
    )
    monkeypatch.setattr(
        entity_service,
        "goal_templates",
        lambda: {
            "enter_tournament": {
                "goal_type": "enter_tournament",
                "completion_mode": "ordered",
                "requires": ["tournament_id"],
                "steps": [],
            }
        },
    )
    monkeypatch.setattr(
        entity_service.entities_repo,
        "add_entity_goal",
        lambda *args: inserted.append({"args": args}),
    )
    return inserted


def test_add_entity_goal_rejects_unknown_goal_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_goal_service_fakes(monkeypatch)

    with pytest.raises(entity_service.UnknownGoalType):
        entity_service.add_entity_goal(
            None,
            1,
            "does_not_exist",
            {},
            3,
            0,
            "ordered",
            None,
            True,
            None,
        )


def test_add_entity_goal_requires_template_payload_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_goal_service_fakes(monkeypatch)

    with pytest.raises(entity_service.MissingGoalPayloadField):
        entity_service.add_entity_goal(
            None,
            1,
            "enter_tournament",
            {},
            3,
            0,
            "ordered",
            None,
            True,
            None,
        )


def test_add_entity_goal_inserts_valid_template_goal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inserted = _install_goal_service_fakes(monkeypatch)

    entity_service.add_entity_goal(
        None,
        1,
        "enter_tournament",
        {"tournament_id": 5},
        3,
        0,
        "ordered",
        None,
        True,
        None,
    )

    assert len(inserted) == 1

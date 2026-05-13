"""Game settings JSON merge, cache refresh, and HTTP API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def game_settings_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "game_settings.json"
    initial = {
        "traits": {"starting_trait_counts": {"0": 40, "1": 40}},
        "simulation": {"day_length_multiplier": 1},
        "balance": {"global_xp_multiplier": 1.0},
        "season_length": 4,
    }
    path.write_text(json.dumps(initial, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr("rts_world.config.GAME_SETTINGS_PATH", path)

    import rts_world.config as config_module

    config_module._SETTINGS_CACHE = None
    yield path
    config_module._SETTINGS_CACHE = None


def test_merge_preserves_unrelated_keys(game_settings_file: Path) -> None:
    from rts_world.config import commit_game_settings, get_game_settings, merge_game_settings_in_memory

    merged = merge_game_settings_in_memory({"simulation": {"day_length_multiplier": 2.5}})
    assert merged["traits"]["starting_trait_counts"]["0"] == 40
    assert merged["simulation"]["day_length_multiplier"] == 2.5
    assert merged["season_length"] == 4
    commit_game_settings(merged)
    on_disk = json.loads(game_settings_file.read_text(encoding="utf-8"))
    assert on_disk["traits"]["starting_trait_counts"]["0"] == 40
    assert get_game_settings(force_reload=True)["simulation"]["day_length_multiplier"] == 2.5


def test_get_game_settings_endpoint(game_settings_file: Path) -> None:
    from fastapi.testclient import TestClient

    from rts_world.api.main import app

    client = TestClient(app)
    response = client.get("/settings/game-settings")
    assert response.status_code == 200
    assert response.json()["simulation"]["day_length_multiplier"] == 1


def test_patch_game_settings_validates_and_saves(game_settings_file: Path) -> None:
    from fastapi.testclient import TestClient

    from rts_world.api.main import app

    client = TestClient(app)
    bad = client.patch("/settings/game-settings", json={"simulation": {"day_length_multiplier": 0}})
    assert bad.status_code == 400

    ok = client.patch(
        "/settings/game-settings",
        json={"simulation": {"day_length_multiplier": 3}},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["settings"]["simulation"]["day_length_multiplier"] == 3
    assert body["real_seconds_per_game_day"] == pytest.approx(20 * 60 * 3, rel=1e-5)

    disk = json.loads(game_settings_file.read_text(encoding="utf-8"))
    assert disk["simulation"]["day_length_multiplier"] == 3


def test_patch_rejects_non_object_simulation_without_writing(game_settings_file: Path) -> None:
    from fastapi.testclient import TestClient

    from rts_world.api.main import app

    before = game_settings_file.read_text(encoding="utf-8")
    client = TestClient(app)
    response = client.patch("/settings/game-settings", json={"simulation": "bad"})
    assert response.status_code == 400
    assert response.json()["detail"] == "simulation must be an object"
    assert game_settings_file.read_text(encoding="utf-8") == before

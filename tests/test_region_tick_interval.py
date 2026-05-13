"""Region tick count and spacing from ``day_length_multiplier``."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from rts_world.sim import clock


def _sim_settings(mult: float) -> dict:
    return {"simulation": {"day_length_multiplier": mult}, "traits": {}, "balance": {}}


def test_ticks_per_game_day_multiplier_one() -> None:
    with patch.object(clock, "get_game_settings", return_value=_sim_settings(1.0)):
        assert clock.day_length_multiplier() == 1.0
        assert clock.ticks_per_game_day() == 5


def test_ticks_per_game_day_multiplier_two() -> None:
    with patch.object(clock, "get_game_settings", return_value=_sim_settings(2.0)):
        assert clock.ticks_per_game_day() == 10


def test_ticks_per_game_day_multiplier_point_two() -> None:
    with patch.object(clock, "get_game_settings", return_value=_sim_settings(0.2)):
        assert clock.ticks_per_game_day() == 1


def test_day_length_multiplier_non_positive_clamps() -> None:
    with patch.object(clock, "get_game_settings", return_value=_sim_settings(0.0)):
        assert clock.day_length_multiplier() == 1.0
        assert clock.ticks_per_game_day() == 5


def test_region_tick_interval_matches_day_length_over_ticks() -> None:
    with patch.object(clock, "get_game_settings", return_value=_sim_settings(2.0)):
        day_sec = clock.real_seconds_per_game_day()
        n = clock.ticks_per_game_day()
        assert clock.region_tick_interval_seconds() == pytest.approx(day_sec / float(n))


def test_region_tick_interval_is_per_region_cadence_window() -> None:
    with patch.object(clock, "get_game_settings", return_value=_sim_settings(1.0)):
        assert clock.ticks_per_game_day() == 5
        assert clock.region_tick_interval_seconds() == pytest.approx(240.0)

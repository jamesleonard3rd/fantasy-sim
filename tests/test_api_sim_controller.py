"""API sim controller cadence behavior."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from rts_world.sim import control
from rts_world.sim.tick import TickResult


class _FakeConnection:
    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_tick_unpaused_regions_ticks_every_region_once_in_oldest_first_order() -> None:
    controller = control.ApiSimController()
    older = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc)
    regions = [
        {"id": 30, "name": "Newer", "last_tick_at": newer},
        {"id": 10, "name": "Never ticked", "last_tick_at": None},
        {"id": 20, "name": "Older", "last_tick_at": older},
    ]

    def fake_tick(region_id: int) -> TickResult:
        return TickResult(region_id=region_id, region_name=f"region-{region_id}")

    with (
        patch.object(control, "get_connection", return_value=_FakeConnection()),
        patch.object(control.regions_repo, "list_unpaused_regions", return_value=regions),
        patch.object(control, "tick_region", side_effect=fake_tick) as tick_region,
    ):
        results = controller._tick_unpaused_regions()

    assert [result.region_id for result in results] == [10, 20, 30]
    assert [call.args[0] for call in tick_region.call_args_list] == [10, 20, 30]


def test_run_loop_waits_for_future_next_tick_before_ticking() -> None:
    controller = control.ApiSimController()
    controller._next_tick_at = datetime.now(timezone.utc) + timedelta(seconds=60)
    wait_delays: list[float] = []

    def fake_wait(delay: float) -> bool:
        wait_delays.append(delay)
        return True

    with (
        patch.object(controller._stop_event, "wait", side_effect=fake_wait),
        patch.object(controller, "_tick_unpaused_regions") as tick_unpaused_regions,
    ):
        controller._run_loop()

    assert wait_delays
    assert wait_delays[0] > 0
    tick_unpaused_regions.assert_not_called()


def test_remaining_delay_is_preserved_for_resume() -> None:
    controller = control.ApiSimController()
    controller._next_tick_at = datetime.now(timezone.utc) + timedelta(seconds=60)

    remaining = controller._remaining_delay_seconds_unlocked()

    assert remaining is not None
    assert 0 < remaining <= 60

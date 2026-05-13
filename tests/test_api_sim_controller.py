"""API sim controller cadence behavior."""
from __future__ import annotations

from datetime import datetime, timezone
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

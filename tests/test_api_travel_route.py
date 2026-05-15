"""GET /travel-route preview (same routing as sim)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from rts_world.api.main import app
from rts_world.sim.travel import TravelSegment


class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, *_args: object, **_kwargs: object) -> None:
        pass

    def fetchall(self) -> list[tuple]:
        return self._rows


class _FakeConn:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)


_REGION_ROWS = [
    (1, "alpha", "Alpha", "region", None),
    (2, "beta", "Beta", "region", None),
    (3, "gamma", "Gamma", "region", None),
]


def test_travel_route_requires_query_params() -> None:
    client = TestClient(app)
    assert client.get("/travel-route").status_code == 422
    assert client.get("/travel-route", params={"from_region_id": 1}).status_code == 422


@patch("rts_world.api.main.get_connection")
def test_travel_route_unknown_region_returns_404(mock_get: object) -> None:
    mock_get.return_value = _FakeConn(_REGION_ROWS)
    client = TestClient(app)
    r = client.get("/travel-route", params={"from_region_id": 99, "to_region_id": 1})
    assert r.status_code == 404


@patch("rts_world.api.main.get_connection")
@patch("rts_world.api.main.route_travel_segments")
def test_travel_route_same_region(
    mock_route: object,
    mock_get: object,
) -> None:
    mock_get.return_value = _FakeConn(_REGION_ROWS)
    mock_route.return_value = []
    client = TestClient(app)
    r = client.get("/travel-route", params={"from_region_id": 1, "to_region_id": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["segments"] == []
    assert body["stop_names"] == []
    assert body["reason"] == "same_region"


@patch("rts_world.api.main.get_connection")
@patch("rts_world.api.main.route_travel_segments")
def test_travel_route_unroutable(
    mock_route: object,
    mock_get: object,
) -> None:
    mock_get.return_value = _FakeConn(_REGION_ROWS)
    mock_route.return_value = None
    client = TestClient(app)
    r = client.get("/travel-route", params={"from_region_id": 1, "to_region_id": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["segments"] is None
    assert body["stop_names"] == []
    assert body["reason"] == "no_route"


@patch("rts_world.api.main.get_connection")
@patch("rts_world.api.main.route_travel_segments")
def test_travel_route_multi_hop_stop_names(
    mock_route: object,
    mock_get: object,
) -> None:
    mock_get.return_value = _FakeConn(_REGION_ROWS)
    mock_route.return_value = [
        TravelSegment(
            from_region_id=1,
            to_region_id=2,
            from_name="Alpha",
            to_name="Beta",
            duration_ticks=3,
            mode="road",
        ),
        TravelSegment(
            from_region_id=2,
            to_region_id=3,
            from_name="Beta",
            to_name="Gamma",
            duration_ticks=2,
            mode="road",
        ),
    ]
    client = TestClient(app)
    r = client.get("/travel-route", params={"from_region_id": 1, "to_region_id": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["reason"] is None
    assert body["stop_names"] == ["Alpha", "Beta", "Gamma"]
    assert len(body["segments"]) == 2
    assert body["segments"][0]["from_region_id"] == 1
    assert body["segments"][1]["to_region_id"] == 3

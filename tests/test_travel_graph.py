from __future__ import annotations

from rts_world.sim.travel import (
    _implicit_local_edges,
    route_travel_segments_from_raw_edges,
)


def test_route_prefers_lower_total_weight() -> None:
    regions_by_id = {
        1: {"id": 1, "key": "a", "name": "A"},
        2: {"id": 2, "key": "b", "name": "B"},
        3: {"id": 3, "key": "c", "name": "C"},
    }
    raw = [
        {"from": "a", "to": "b", "base_ticks": 100, "bidirectional": True},
        {"from": "a", "to": "c", "base_ticks": 1, "bidirectional": True},
        {"from": "c", "to": "b", "base_ticks": 1, "bidirectional": True},
    ]
    path = route_travel_segments_from_raw_edges(raw, 1, 2, regions_by_id)
    assert path is not None
    assert [s.to_region_id for s in path] == [3, 2]
    assert sum(s.duration_ticks for s in path) == 2


def test_zero_tick_edge_is_preserved() -> None:
    regions_by_id = {
        1: {"id": 1, "key": "a", "name": "A"},
        2: {"id": 2, "key": "b", "name": "B"},
    }
    raw = [{"from": "a", "to": "b", "base_ticks": 0, "bidirectional": True}]
    path = route_travel_segments_from_raw_edges(raw, 1, 2, regions_by_id)
    assert path is not None
    assert len(path) == 1
    assert path[0].duration_ticks == 0


def test_bidirectional_edge_allows_reverse() -> None:
    regions_by_id = {
        1: {"id": 1, "key": "x", "name": "X"},
        2: {"id": 2, "key": "y", "name": "Y"},
    }
    raw = [{"from": "x", "to": "y", "base_ticks": 5, "bidirectional": True}]
    path = route_travel_segments_from_raw_edges(raw, 2, 1, regions_by_id)
    assert path is not None
    assert len(path) == 1
    assert path[0].from_region_id == 2
    assert path[0].to_region_id == 1
    assert path[0].duration_ticks == 5


def test_unknown_endpoint_names_skip_edge() -> None:
    regions_by_id = {
        1: {"id": 1, "key": "a", "name": "A"},
        2: {"id": 2, "key": "b", "name": "B"},
    }
    raw = [
        {"from": "a", "to": "ghost_town", "base_ticks": 1, "bidirectional": True},
        {"from": "a", "to": "b", "base_ticks": 3, "bidirectional": True},
    ]
    path = route_travel_segments_from_raw_edges(raw, 1, 2, regions_by_id)
    assert path is not None
    assert len(path) == 1
    assert path[0].duration_ticks == 3


def test_unroutable_returns_none() -> None:
    regions_by_id = {
        1: {"id": 1, "key": "a", "name": "A"},
        2: {"id": 2, "key": "b", "name": "B"},
        3: {"id": 3, "key": "c", "name": "C"},
    }
    raw = [{"from": "a", "to": "b", "base_ticks": 1, "bidirectional": True}]
    assert route_travel_segments_from_raw_edges(raw, 1, 3, regions_by_id) is None


def test_same_city_descendants_route_locally_without_authored_edge() -> None:
    regions_by_id = {
        1: {"id": 1, "key": "valemont_keep", "name": "Valemont Keep", "type": "castle", "parent_id": None},
        2: {"id": 2, "key": "valemont_keep.gatehouse", "name": "Gatehouse", "type": "district", "parent_id": 1},
        3: {"id": 3, "key": "valemont_keep.barracks", "name": "Barracks", "type": "district", "parent_id": 1},
    }

    path = route_travel_segments_from_raw_edges([], 2, 3, regions_by_id)

    assert path is not None
    assert len(path) == 1
    assert path[0].from_region_id == 2
    assert path[0].to_region_id == 3
    assert path[0].duration_ticks == 0
    assert path[0].mode == "local"


def test_nested_city_descendants_route_to_nearest_local_group_root() -> None:
    regions_by_id = {
        1: {"id": 1, "key": "whisperwood_marches", "name": "Whisperwood Marches", "type": "region", "parent_id": None},
        2: {"id": 2, "key": "valemont_keep", "name": "Valemont Keep", "type": "castle", "parent_id": 1},
        3: {"id": 3, "key": "valemont_keep.inner_ward", "name": "Inner Ward", "type": "district", "parent_id": 2},
        4: {"id": 4, "key": "valemont_keep.training_yard", "name": "Training Yard", "type": "room", "parent_id": 3},
        5: {"id": 5, "key": "valemont_keep.armory", "name": "Armory", "type": "room", "parent_id": 3},
    }

    path = route_travel_segments_from_raw_edges([], 4, 5, regions_by_id)

    assert path is not None
    assert len(path) == 1
    assert path[0].duration_ticks == 0
    assert path[0].mode == "local"


def test_different_city_roots_do_not_route_locally() -> None:
    regions_by_id = {
        1: {"id": 1, "key": "valemont_keep", "name": "Valemont Keep", "type": "castle", "parent_id": None},
        2: {"id": 2, "key": "valemont_keep.barracks", "name": "Barracks", "type": "district", "parent_id": 1},
        3: {"id": 3, "key": "frostpine_town", "name": "Frostpine Town", "type": "town", "parent_id": None},
        4: {"id": 4, "key": "frostpine_town.barracks", "name": "Barracks", "type": "district", "parent_id": 3},
    }

    assert route_travel_segments_from_raw_edges([], 2, 4, regions_by_id) is None


def test_authored_external_edges_combine_with_implicit_local_edges() -> None:
    regions_by_id = {
        1: {"id": 1, "key": "valemont_keep", "name": "Valemont Keep", "type": "castle", "parent_id": None},
        2: {"id": 2, "key": "valemont_keep.gatehouse", "name": "Gatehouse", "type": "district", "parent_id": 1},
        3: {"id": 3, "key": "whisperwood_road", "name": "Whisperwood Road", "type": "border", "parent_id": None},
    }
    raw = [
        {
            "from": "valemont_keep",
            "to": "whisperwood_road",
            "base_ticks": 10,
            "bidirectional": True,
            "mode": "gate",
        }
    ]

    path = route_travel_segments_from_raw_edges(raw, 2, 3, regions_by_id)

    assert path is not None
    assert [(s.from_region_id, s.to_region_id, s.duration_ticks, s.mode) for s in path] == [
        (2, 1, 0, "local"),
        (1, 3, 10, "gate"),
    ]


def test_implicit_local_edges_scale_linearly_with_city_size() -> None:
    regions_by_id = {
        1: {"id": 1, "key": "big_city", "name": "Big City", "type": "city", "parent_id": None},
    }
    for region_id in range(2, 102):
        regions_by_id[region_id] = {
            "id": region_id,
            "key": f"big_city.district_{region_id}",
            "name": f"District {region_id}",
            "type": "district",
            "parent_id": 1,
        }

    edges = _implicit_local_edges(regions_by_id)

    assert len(edges) == 200


def test_duplicate_display_names_route_by_key_not_name() -> None:
    regions_by_id = {
        1: {"id": 1, "key": "valemont_keep", "name": "Valemont Keep", "type": "castle", "parent_id": None},
        2: {"id": 2, "key": "valemont_keep.barracks", "name": "Barracks", "type": "district", "parent_id": 1},
        3: {"id": 3, "key": "frostpine_keep", "name": "Frostpine Keep", "type": "castle", "parent_id": None},
        4: {"id": 4, "key": "frostpine_keep.barracks", "name": "Barracks", "type": "district", "parent_id": 3},
    }
    raw = [
        {
            "from": "valemont_keep.barracks",
            "to": "frostpine_keep.barracks",
            "base_ticks": 50,
            "bidirectional": True,
        }
    ]

    path = route_travel_segments_from_raw_edges(raw, 2, 4, regions_by_id)

    assert path is not None
    assert len(path) == 1
    assert path[0].from_name == "Barracks"
    assert path[0].to_name == "Barracks"
    assert path[0].duration_ticks == 50

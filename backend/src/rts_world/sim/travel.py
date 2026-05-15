"""Travel graph from ``game_data/regions/templates.json`` ``travel_edges``."""
from __future__ import annotations

import json
import heapq
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[4]
REGIONS_TEMPLATES_FILE = PROJECT_DIR / "game_data" / "regions" / "templates.json"
LOCAL_TRAVEL_GROUP_ROOT_TYPES = {"castle", "city", "settlement", "town"}
LOCAL_TRAVEL_MODE = "local"


@dataclass(frozen=True)
class TravelSegment:
    """One hop along a resolved route (region IDs are DB ids)."""

    from_region_id: int
    to_region_id: int
    from_name: str
    to_name: str
    duration_ticks: int
    mode: str


def clear_travel_graph_cache() -> None:
    """Clear cached JSON load (for tests that patch game data)."""
    _load_travel_edges_json.cache_clear()


@lru_cache(maxsize=1)
def _load_travel_edges_json() -> list[dict[str, Any]]:
    if not REGIONS_TEMPLATES_FILE.is_file():
        return []
    data = json.loads(REGIONS_TEMPLATES_FILE.read_text(encoding="utf-8"))
    raw = data.get("travel_edges")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    return out


def _ref_to_region_id(regions_by_id: dict[int, dict[str, Any]]) -> dict[str, int]:
    """Map stable keys and unambiguous legacy names to region ids."""
    refs: dict[str, int] = {}
    name_counts: dict[str, int] = {}
    for rid, row in regions_by_id.items():
        key = row.get("key")
        if isinstance(key, str) and key:
            refs[key] = int(rid)
        name = row.get("name")
        if isinstance(name, str) and name:
            name_counts[name] = name_counts.get(name, 0) + 1
    for rid, row in regions_by_id.items():
        name = row.get("name")
        if isinstance(name, str) and name and name_counts.get(name) == 1:
            refs.setdefault(name, int(rid))
    return refs


def _parse_edges_for_routing(
    raw_edges: list[dict[str, Any]],
    ref_to_id: dict[str, int],
) -> list[tuple[int, int, int, str]]:
    """Directed edges as (from_id, to_id, weight, mode); skips unknown refs."""
    directed: list[tuple[int, int, int, str]] = []
    for edge in raw_edges:
        a = edge.get("from")
        b = edge.get("to")
        if not isinstance(a, str) or not isinstance(b, str):
            continue
        ia = ref_to_id.get(a)
        ib = ref_to_id.get(b)
        if ia is None or ib is None:
            continue
        try:
            w = int(edge.get("base_ticks", 1))
        except (TypeError, ValueError):
            w = 1
        w = max(0, w)
        mode = edge.get("mode")
        mode_s = str(mode) if mode is not None else "road"
        directed.append((ia, ib, w, mode_s))
        if bool(edge.get("bidirectional", True)):
            directed.append((ib, ia, w, mode_s))
    return directed


def _region_type(row: dict[str, Any]) -> str:
    value = row.get("type", row.get("kind", ""))
    return str(value).lower() if value is not None else ""


def _parent_by_region_id(regions_by_id: dict[int, dict[str, Any]]) -> dict[int, int]:
    parents: dict[int, int] = {}
    for rid, row in regions_by_id.items():
        parent_id = row.get("parent_id")
        if parent_id is None:
            continue
        try:
            parent_int = int(parent_id)
        except (TypeError, ValueError):
            continue
        if parent_int in regions_by_id and parent_int != int(rid):
            parents[int(rid)] = parent_int
    return parents


def _local_group_by_region_id(regions_by_id: dict[int, dict[str, Any]]) -> dict[int, int]:
    """Map each region to its nearest city/castle-style ancestor, if any."""
    parent_by_id = _parent_by_region_id(regions_by_id)
    group_by_id: dict[int, int] = {}

    for rid, row in regions_by_id.items():
        current = int(rid)
        seen: set[int] = set()
        if _region_type(row) in LOCAL_TRAVEL_GROUP_ROOT_TYPES:
            group_by_id[int(rid)] = int(rid)
            continue

        while current in parent_by_id and current not in seen:
            seen.add(current)
            current = parent_by_id[current]
            parent_row = regions_by_id.get(current)
            if parent_row is None:
                break
            if _region_type(parent_row) in LOCAL_TRAVEL_GROUP_ROOT_TYPES:
                group_by_id[int(rid)] = current
                break

    return group_by_id


def _implicit_local_edges(
    regions_by_id: dict[int, dict[str, Any]],
) -> list[tuple[int, int, int, str]]:
    """Zero-cost star edges from each local-group member to its group root."""
    edges: list[tuple[int, int, int, str]] = []
    for member_id, root_id in _local_group_by_region_id(regions_by_id).items():
        if member_id == root_id:
            continue
        edges.append((member_id, root_id, 0, LOCAL_TRAVEL_MODE))
        edges.append((root_id, member_id, 0, LOCAL_TRAVEL_MODE))
    return edges


def _same_local_group_segment(
    start: int,
    end: int,
    regions_by_id: dict[int, dict[str, Any]],
    id_to_name: dict[int, str],
) -> TravelSegment | None:
    groups = _local_group_by_region_id(regions_by_id)
    start_group = groups.get(start)
    if start_group is None or groups.get(end) != start_group:
        return None
    return TravelSegment(
        from_region_id=start,
        to_region_id=end,
        from_name=id_to_name.get(start, str(start)),
        to_name=id_to_name.get(end, str(end)),
        duration_ticks=0,
        mode=LOCAL_TRAVEL_MODE,
    )


def _dijkstra(
    edges: list[tuple[int, int, int, str]],
    start: int,
    end: int,
    id_to_name: dict[int, str],
) -> list[TravelSegment] | None:
    if start == end:
        return []

    adj: dict[int, list[tuple[int, int, str]]] = {}
    for u, v, w, m in edges:
        adj.setdefault(u, []).append((v, w, m))

    dist: dict[int, int] = {start: 0}
    prev: dict[int, tuple[int, int, str] | None] = {start: None}
    heap: list[tuple[int, int]] = [(0, start)]

    while heap:
        d, u = heapq.heappop(heap)
        if d != dist.get(u, 10**18):
            continue
        if u == end:
            break
        for v, w, m in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, 10**18):
                dist[v] = nd
                prev[v] = (u, w, m)
                heapq.heappush(heap, (nd, v))

    if end not in prev and start != end:
        return None

    hops: list[tuple[int, int, int, str]] = []
    cur = end
    while cur != start:
        p = prev.get(cur)
        if p is None:
            return None
        u, w, m = p
        hops.append((u, cur, w, m))
        cur = u
    hops.reverse()

    out: list[TravelSegment] = []
    for u, v, w, m in hops:
        out.append(
            TravelSegment(
                from_region_id=u,
                to_region_id=v,
                from_name=id_to_name.get(u, str(u)),
                to_name=id_to_name.get(v, str(v)),
                duration_ticks=w,
                mode=m,
            )
        )
    return out


def route_travel_segments(
    start_region_id: int | None,
    end_region_id: int,
    regions_by_id: dict[int, dict[str, Any]],
) -> list[TravelSegment] | None:
    """Return cheapest path by total ``base_ticks``, or ``None`` if unroutable.

    ``start_region_id`` may be ``None`` (entity has no region): no route.
    """
    if start_region_id is None:
        return None
    s = int(start_region_id)
    t = int(end_region_id)
    if s == t:
        return []

    ref_to_id = _ref_to_region_id(regions_by_id)
    if not ref_to_id:
        return None

    raw = _load_travel_edges_json()
    return route_travel_segments_from_raw_edges(raw, start_region_id, end_region_id, regions_by_id)


def route_travel_segments_from_raw_edges(
    raw_edges: list[dict[str, Any]],
    start_region_id: int | None,
    end_region_id: int,
    regions_by_id: dict[int, dict[str, Any]],
) -> list[TravelSegment] | None:
    """Route using an explicit edge list (for tests); same rules as :func:`route_travel_segments`."""
    if start_region_id is None:
        return None
    s = int(start_region_id)
    t = int(end_region_id)
    if s == t:
        return []

    ref_to_id = _ref_to_region_id(regions_by_id)
    if not ref_to_id:
        return None

    id_to_name = {int(rid): str(row.get("name", str(rid))) for rid, row in regions_by_id.items()}
    local_segment = _same_local_group_segment(s, t, regions_by_id, id_to_name)
    if local_segment is not None:
        return [local_segment]

    edges = _parse_edges_for_routing(raw_edges, ref_to_id)
    edges.extend(_implicit_local_edges(regions_by_id))
    return _dijkstra(edges, s, t, id_to_name)

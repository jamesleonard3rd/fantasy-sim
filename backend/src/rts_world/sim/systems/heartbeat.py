"""Stub system that proves the pipeline end-to-end.

Emits a single ``region.tick`` event each tick with the entity count and the
game clock. This is the system the MVP test asserts on (roadmap §8.8). Once
real systems land (opinion drift, needs, etc.) this can stay as a cheap
heartbeat or be removed — your call.
"""
from __future__ import annotations

from ..state import PendingEvent, RegionState, TickContext


def heartbeat(state: RegionState, ctx: TickContext) -> list[PendingEvent]:
    return [
        PendingEvent(
            kind="region.tick",
            significance=1,
            payload={
                "region_id": state.region_id,
                "region_name": state.region["name"],
                "entity_count": len(state.entities),
                "game_day": ctx.game_day,
                "game_tick": ctx.game_tick,
            },
        )
    ]

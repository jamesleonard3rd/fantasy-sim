"""Sim systems: pure functions over RegionState.

Each system is a small file in this package that exposes a callable matching
the ``System`` protocol. Adding a behaviour is "drop a file in here, register
it in ``default_systems()``". Systems must:

    * be deterministic given (state, ctx) — use ``ctx.rng``, never ``random``;
    * mutate ``state`` in place AND mark dirty rows on it;
    * emit ``PendingEvent`` rows by *returning* them, never by writing to the DB.

The DB is the orchestrator's problem. Systems should not import services or
repositories; those layers belong at API/script/orchestration edges and in the
region writeback path.
"""
from __future__ import annotations

from typing import Callable, Sequence

from ..state import PendingEvent, RegionState, TickContext


# A system is just a callable: (state, ctx) -> events.
# We attach a ``.name`` attribute (or .__name__) for logging.
System = Callable[[RegionState, TickContext], list[PendingEvent]]


def default_systems() -> Sequence[System]:
    """Systems run in this order, every region tick.

    Keep the list short and explicit. Adding a real system means importing it
    here and inserting it in dependency order.
    """
    from .heartbeat import heartbeat  # local import keeps package import cheap
    from .factions import faction_behavior
    from .goals import goal_brain
    from .relationships import relationship_dynamics
    from .tournaments import tournament_system

    return (relationship_dynamics, faction_behavior, goal_brain, tournament_system, heartbeat)

"""World clock: shared in-game time used by every system.

Single-row table ``world_clock``. The scheduler bumps ``game_tick`` (and
``game_day`` when it rolls over) once per region tick. Systems read game
time from here rather than ``datetime.now()`` so behaviour is deterministic
in tests.

Only this module is allowed to write ``world_clock``.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg


# In-game days per real-time wall-clock advance is purely a knob; we keep
# the conversion explicit and conservative. 1 game day per 240 ticks roughly
# matches "a region ticks every ~3 minutes -> ~12 hours of game time per real
# day" without committing the design to anything yet. Adjust freely.
TICKS_PER_GAME_DAY: int = 240


@dataclass(frozen=True)
class WorldClock:
    game_day: int
    game_tick: int


def read_clock(conn: psycopg.Connection) -> WorldClock:
    """Return the current world clock. Cheap; one row, primary-key lookup."""
    with conn.cursor() as cur:
        cur.execute("SELECT game_day, game_tick FROM world_clock WHERE id = 1")
        row = cur.fetchone()
        if row is None:
            # Schema seeds this row, but be defensive in case someone wiped it.
            cur.execute(
                "INSERT INTO world_clock (id, game_day, game_tick) "
                "VALUES (1, 0, 0) ON CONFLICT (id) DO NOTHING"
            )
            return WorldClock(game_day=0, game_tick=0)
        return WorldClock(game_day=int(row[0]), game_tick=int(row[1]))


def advance_clock(conn: psycopg.Connection) -> WorldClock:
    """Bump game_tick by 1, rolling game_day when it crosses TICKS_PER_GAME_DAY.

    Returns the *new* clock value. Caller is responsible for committing — the
    tick orchestrator wraps load + simulate + write + advance in one
    BEGIN/COMMIT.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE world_clock
               SET game_tick = game_tick + 1,
                   game_day  = game_day + ((game_tick + 1) / %s)::int
                              - (game_tick / %s)::int,
                   updated_at = NOW()
             WHERE id = 1
            RETURNING game_day, game_tick
            """,
            (TICKS_PER_GAME_DAY, TICKS_PER_GAME_DAY),
        )
        row = cur.fetchone()
        if row is None:
            # world_clock row missing — recreate and recurse once.
            cur.execute(
                "INSERT INTO world_clock (id, game_day, game_tick) "
                "VALUES (1, 0, 1) ON CONFLICT (id) DO NOTHING"
            )
            return WorldClock(game_day=0, game_tick=1)
        return WorldClock(game_day=int(row[0]), game_tick=int(row[1]))

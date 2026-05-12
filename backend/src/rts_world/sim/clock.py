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


# The visible sim clock is a normal 24-hour day. One real-world minute equals
# one full in-game day, so one real-world second advances the clock 24 minutes.
GAME_MINUTES_PER_DAY: int = 24 * 60
GAME_MINUTES_PER_REAL_SECOND: int = 24


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
    """Advance the stored clock based on wall time since its last update.

    Returns the *new* clock value. Caller is responsible for committing — the
    tick orchestrator wraps load + simulate + write + advance in one
    BEGIN/COMMIT.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH current_clock AS (
                SELECT game_day,
                       game_tick,
                       GREATEST(
                           1,
                           ROUND(EXTRACT(EPOCH FROM (NOW() - updated_at)) * %s)::bigint
                       ) AS elapsed_game_minutes
                  FROM world_clock
                 WHERE id = 1
            ),
            next_clock AS (
                SELECT game_day * %s + game_tick + elapsed_game_minutes AS total_minutes
                  FROM current_clock
            )
            UPDATE world_clock wc
               SET game_day = (next_clock.total_minutes / %s)::int,
                   game_tick = MOD(next_clock.total_minutes, %s),
                   updated_at = NOW()
              FROM next_clock
             WHERE wc.id = 1
            RETURNING game_day, game_tick
            """,
            (
                GAME_MINUTES_PER_REAL_SECOND,
                GAME_MINUTES_PER_DAY,
                GAME_MINUTES_PER_DAY,
                GAME_MINUTES_PER_DAY,
            ),
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


def touch_clock(conn: psycopg.Connection) -> None:
    """Reset the wall-clock anchor without advancing game time."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO world_clock (id, game_day, game_tick, updated_at)
            VALUES (1, 0, 0, NOW())
            ON CONFLICT (id) DO UPDATE
                SET updated_at = NOW()
            """
        )

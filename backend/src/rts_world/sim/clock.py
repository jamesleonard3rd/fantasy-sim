"""World clock: shared in-game time used by every system.

Single-row table ``world_clock``. Each successful region tick commits an
``advance_clock`` that maps wall time since ``updated_at`` into in-game minutes.

Day length is configured by ``game_data/config/game_settings.json``:
``simulation.day_length_multiplier`` scales the base rate of **20 real minutes
per full in-game day** (multiplier > 1 stretches a realm day in real time).

Only this module is allowed to write ``world_clock``.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg

from ..config import get_game_settings

# One realm day is always 24 × 60 in-world minutes; ``game_tick`` is minute-of-day.
GAME_MINUTES_PER_DAY: int = 24 * 60

# Default when settings omit the key: 20 real minutes per game day, multiplier 1.
_BASE_REAL_MINUTES_PER_GAME_DAY: float = 20.0

# API sim loop: region ticks per full in-game day scales with ``day_length_multiplier``.
# With the default 20 real minutes per game day, 5 ticks/day yields a 240s cadence.
BASE_TICKS_PER_GAME_DAY: int = 5


def day_length_multiplier() -> float:
    """``simulation.day_length_multiplier`` from game settings, clamped to positive."""
    sim = get_game_settings().get("simulation") or {}
    mult = float(sim.get("day_length_multiplier", 1.0))
    if mult <= 0:
        mult = 1.0
    return mult


def real_seconds_per_game_day() -> float:
    """Wall-clock seconds that span one full in-game day (24h realm time)."""
    return _BASE_REAL_MINUTES_PER_GAME_DAY * 60.0 * day_length_multiplier()


def ticks_per_game_day() -> int:
    """How many region ticks to schedule per full in-game day (longer days => more ticks)."""
    return max(1, round(BASE_TICKS_PER_GAME_DAY * day_length_multiplier()))


def region_tick_interval_seconds() -> float:
    """Wall seconds between API sim region tick attempts for the current settings."""
    n = ticks_per_game_day()
    return real_seconds_per_game_day() / float(n)


def game_minutes_per_real_second() -> float:
    """How many in-game minutes advance per one real-time second."""
    return float(GAME_MINUTES_PER_DAY) / real_seconds_per_game_day()


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
                game_minutes_per_real_second(),
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

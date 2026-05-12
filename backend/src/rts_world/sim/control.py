"""API-owned simulation loop for frontend start/stop controls."""
from __future__ import annotations

import random
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ..db.db import get_connection
from . import regions as regions_repo
from .clock import advance_clock, touch_clock
from .events import bulk_insert_events
from .state import PendingEvent
from .tick import TickResult, tick_region


DEFAULT_MIN_INTERVAL_SECONDS = 15.0
DEFAULT_MAX_INTERVAL_SECONDS = 30.0

TIDING_TEMPLATES = (
    "{name} was seen studying the old maps by candlelight.",
    "{name} traded rumors with a passing courier.",
    "{name} spent the afternoon avoiding unwanted attention.",
    "{name} made a quiet promise that may matter later.",
    "{name} heard whispers of trouble beyond the road.",
    "{name} found a reason to smile before dusk.",
)


@dataclass
class SimStatus:
    running: bool
    tick_count: int
    min_interval_seconds: float
    max_interval_seconds: float
    next_tick_at: datetime | None
    last_tick_at: datetime | None
    last_region_id: int | None
    last_region_name: str | None
    last_game_day: int | None
    last_game_tick: int | None
    last_events_emitted: int
    last_error: str | None


class ApiSimController:
    """Thread-backed sim loop controlled through the FastAPI process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._tick_count = 0
        self._min_interval = DEFAULT_MIN_INTERVAL_SECONDS
        self._max_interval = DEFAULT_MAX_INTERVAL_SECONDS
        self._next_tick_at: datetime | None = None
        self._last_tick_at: datetime | None = None
        self._last_result: TickResult | None = None
        self._last_error: str | None = None

    def start(
        self,
        *,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        max_interval_seconds: float = DEFAULT_MAX_INTERVAL_SECONDS,
    ) -> SimStatus:
        min_interval = max(1.0, float(min_interval_seconds))
        max_interval = max(min_interval, float(max_interval_seconds))

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._status_unlocked()

            self._min_interval = min_interval
            self._max_interval = max_interval
            self._next_tick_at = datetime.now(timezone.utc)
            self._last_error = None
            with get_connection() as conn:
                touch_clock(conn)
                conn.commit()
            self._stop_event = threading.Event()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="fantasy-sim-api-loop",
                daemon=True,
            )
            self._thread.start()
            return self._status_unlocked()

    def stop(self) -> SimStatus:
        with self._lock:
            thread = self._thread
            was_running = thread is not None and thread.is_alive()
            if not was_running:
                self._next_tick_at = None
                return self._status_unlocked()
            self._stop_event.set()

        thread.join(timeout=2.0)
        stopped = not thread.is_alive()

        if stopped:
            with get_connection() as conn:
                advance_clock(conn)
                conn.commit()

        with self._lock:
            if stopped:
                self._thread = None
                self._next_tick_at = None
            return self._status_unlocked()

    def status(self) -> SimStatus:
        with self._lock:
            return self._status_unlocked()

    def _status_unlocked(self) -> SimStatus:
        thread = self._thread
        running = thread is not None and thread.is_alive()
        last = self._last_result
        return SimStatus(
            running=running,
            tick_count=self._tick_count,
            min_interval_seconds=self._min_interval,
            max_interval_seconds=self._max_interval,
            next_tick_at=self._next_tick_at if running else None,
            last_tick_at=self._last_tick_at,
            last_region_id=last.region_id if last and not last.skipped else None,
            last_region_name=last.region_name if last and not last.skipped else None,
            last_game_day=last.game_day if last and not last.skipped else None,
            last_game_tick=last.game_tick if last and not last.skipped else None,
            last_events_emitted=last.events_emitted if last and not last.skipped else 0,
            last_error=self._last_error,
        )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                result = self._tick_next_region()
                with self._lock:
                    self._last_error = None
                    if result is not None:
                        self._tick_count += 1
                        self._last_tick_at = datetime.now(timezone.utc)
                        self._last_result = result
            except Exception as exc:  # noqa: BLE001 - keep loop alive for frontend control
                with self._lock:
                    self._last_error = str(exc)

            delay = random.uniform(self._min_interval, self._max_interval)
            with self._lock:
                self._next_tick_at = datetime.fromtimestamp(
                    time.time() + delay,
                    tz=timezone.utc,
                )
            self._stop_event.wait(delay)

        with self._lock:
            self._next_tick_at = None

    def _tick_next_region(self) -> TickResult | None:
        with get_connection() as conn:
            regions = regions_repo.list_unpaused_regions(conn)

        if not regions:
            raise RuntimeError("No unpaused regions are available to tick.")

        target = min(
            regions,
            key=lambda region: (
                region["last_tick_at"] is not None,
                region["last_tick_at"] or datetime.min.replace(tzinfo=timezone.utc),
                int(region["id"]),
            ),
        )
        result = tick_region(int(target["id"]))
        if result is not None and not result.skipped:
            self._insert_random_tiding(result.region_id)
        return result

    def _insert_random_tiding(self, region_id: int) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.id, e.name
                      FROM entities e
                      LEFT JOIN entity_zones z ON z.entity_id = e.id
                     WHERE z.region_id = %s OR z.region_id IS NULL
                     ORDER BY random()
                     LIMIT 1
                    """,
                    (region_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return

                entity_id = int(row[0])
                entity_name = str(row[1])
                message = random.choice(TIDING_TEMPLATES).format(name=entity_name)
                bulk_insert_events(
                    conn,
                    region_id,
                    [
                        PendingEvent(
                            kind="realm.tiding",
                            significance=2,
                            subject_entity_id=entity_id,
                            payload={"message": message, "entity_name": entity_name},
                        )
                    ],
                )
            conn.commit()


sim_controller = ApiSimController()


def sim_status_dict(status: SimStatus) -> dict[str, Any]:
    return asdict(status)

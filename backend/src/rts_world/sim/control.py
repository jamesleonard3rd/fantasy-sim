"""API-owned simulation loop for frontend start/stop controls."""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ..db.db import get_connection
from . import regions as regions_repo
from .clock import advance_clock, region_tick_interval_seconds, ticks_per_game_day, touch_clock
from .tick import TickResult, tick_region


@dataclass
class SimStatus:
    running: bool
    tick_count: int
    ticks_per_game_day: int
    tick_interval_seconds: float
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
        self._next_tick_at: datetime | None = None
        self._resume_delay_seconds: float | None = None
        self._last_tick_at: datetime | None = None
        self._last_result: TickResult | None = None
        self._last_error: str | None = None

    def start(self) -> SimStatus:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._status_unlocked()

            now = datetime.now(timezone.utc)
            if self._resume_delay_seconds is None:
                self._next_tick_at = now
            else:
                self._next_tick_at = now + timedelta(
                    seconds=max(0.0, self._resume_delay_seconds)
                )
            self._resume_delay_seconds = None
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
            self._resume_delay_seconds = self._remaining_delay_seconds_unlocked()
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
            ticks_per_game_day=ticks_per_game_day(),
            tick_interval_seconds=region_tick_interval_seconds(),
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
            with self._lock:
                next_tick_at = self._next_tick_at
            if next_tick_at is not None:
                delay = max(
                    0.0,
                    (next_tick_at - datetime.now(timezone.utc)).total_seconds(),
                )
                if self._stop_event.wait(delay):
                    break

            try:
                results = self._tick_unpaused_regions()
                with self._lock:
                    self._last_error = None
                    if results:
                        self._tick_count += len(results)
                        self._last_tick_at = datetime.now(timezone.utc)
                        self._last_result = next(
                            (result for result in reversed(results) if not result.skipped),
                            results[-1],
                        )
            except Exception as exc:  # noqa: BLE001 - keep loop alive for frontend control
                with self._lock:
                    self._last_error = str(exc)

            delay = region_tick_interval_seconds()
            with self._lock:
                self._next_tick_at = datetime.fromtimestamp(
                    time.time() + delay,
                    tz=timezone.utc,
                )
            self._stop_event.wait(delay)

        with self._lock:
            self._next_tick_at = None

    def _remaining_delay_seconds_unlocked(self) -> float | None:
        if self._next_tick_at is None:
            return None
        return max(
            0.0,
            (self._next_tick_at - datetime.now(timezone.utc)).total_seconds(),
        )

    def _tick_unpaused_regions(self) -> list[TickResult]:
        with get_connection() as conn:
            regions = regions_repo.list_unpaused_regions(conn)

        if not regions:
            raise RuntimeError("No unpaused regions are available to tick.")

        ordered_regions = sorted(
            regions,
            key=lambda region: (
                region["last_tick_at"] is not None,
                region["last_tick_at"] or datetime.min.replace(tzinfo=timezone.utc),
                int(region["id"]),
            ),
        )
        results: list[TickResult] = []
        for region in ordered_regions:
            if self._stop_event.is_set():
                break
            results.append(tick_region(int(region["id"])))
        return results


sim_controller = ApiSimController()


def sim_status_dict(status: SimStatus) -> dict[str, Any]:
    return asdict(status)

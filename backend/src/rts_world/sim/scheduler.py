"""Heap-based "next region due" loop (roadmap §5.2).

One thread, one heap of ``(due_at_unix, region_id)``. Pop the soonest, sleep
until due, tick it, push it back with ``now + tick_interval_seconds``. The
heap is rebuilt periodically so newly-created or un-paused regions get
picked up without requiring a restart.

Stutter-free coexistence with Unreal (roadmap §4) comes from three things
the scheduler does NOT do:

    * does not hold a transaction open between ticks (the orchestrator owns
      one BEGIN/COMMIT per tick);
    * does not poll the DB in a tight loop (sleeps to the next due time);
    * does not do anything per-frame — the smallest unit of work is a whole
      region tick.
"""
from __future__ import annotations

import heapq
import logging
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from types import FrameType
from typing import Sequence

from ..db.db import get_connection
from . import regions as regions_repo
from .tick import TickResult, tick_region


log = logging.getLogger(__name__)


# Hard ceiling on per-sleep duration, so SIGINT / region churn / clock skew
# is noticed within a bounded interval. The scheduler will wake, observe,
# and (usually) go right back to sleep.
MAX_SLEEP_SECONDS: float = 5.0

# How often (seconds) to rebuild the heap from the regions table. Keeps
# newly-inserted or un-paused regions from being orphaned indefinitely.
QUEUE_REFRESH_SECONDS: float = 30.0


@dataclass(order=True)
class _HeapEntry:
    due_at: float
    region_id: int


class Scheduler:
    """Long-lived loop. Construct, then call ``run_forever`` (or ``run_once``)."""

    def __init__(self, *, refresh_seconds: float = QUEUE_REFRESH_SECONDS) -> None:
        self._heap: list[_HeapEntry] = []
        self._scheduled_ids: set[int] = set()
        self._refresh_seconds: float = refresh_seconds
        self._last_refresh_at: float = 0.0
        self._stopping: bool = False

    # ---------- public API ----------

    def run_forever(self) -> None:
        """Block forever, ticking due regions. SIGINT exits cleanly."""
        self._install_signal_handlers()
        log.info("sim scheduler starting")
        self._refresh_queue()
        while not self._stopping:
            self._tick_one_due()
        log.info("sim scheduler stopped")

    def run_once(self) -> TickResult | None:
        """Tick the single most-overdue region (if any) and return. For tests."""
        self._refresh_queue()
        if not self._heap:
            return None
        entry = heapq.heappop(self._heap)
        self._scheduled_ids.discard(entry.region_id)
        return self._tick_and_reschedule(entry.region_id)

    def stop(self) -> None:
        self._stopping = True

    # ---------- internals ----------

    def _install_signal_handlers(self) -> None:
        def _handler(signum: int, frame: FrameType | None) -> None:
            log.info("received signal %s, stopping scheduler", signum)
            self.stop()

        # SIGTERM may not exist on Windows; guard.
        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                try:
                    signal.signal(sig, _handler)
                except (ValueError, OSError):
                    # Not in main thread, or platform doesn't support it.
                    pass

    def _refresh_queue(self) -> None:
        """Pull the current set of unpaused regions and (re)schedule any new ones."""
        try:
            with get_connection() as conn:
                regions = regions_repo.list_unpaused_regions(conn)
        except Exception:
            log.exception("failed to refresh region queue")
            return

        live_ids: set[int] = set()
        now_wall = time.time()
        for region in regions:
            region_id = int(region["id"])
            live_ids.add(region_id)
            if region_id in self._scheduled_ids:
                continue
            interval = float(region["tick_interval_seconds"])
            last_tick = region["last_tick_at"]
            if last_tick is None:
                due_at = now_wall  # never ticked -> immediate
            else:
                # last_tick is a tz-aware datetime from Postgres; convert to unix
                lt = _to_aware_utc(last_tick)
                due_at = lt.timestamp() + interval
            heapq.heappush(self._heap, _HeapEntry(due_at=due_at, region_id=region_id))
            self._scheduled_ids.add(region_id)

        # Drop scheduled regions that have been paused or deleted.
        if live_ids != self._scheduled_ids:
            self._heap = [e for e in self._heap if e.region_id in live_ids]
            heapq.heapify(self._heap)
            self._scheduled_ids = {e.region_id for e in self._heap}

        self._last_refresh_at = now_wall

    def _tick_one_due(self) -> None:
        """Pop the next due region, sleep until then, tick it, requeue."""
        # Periodic refresh so new/un-paused regions get picked up.
        if time.time() - self._last_refresh_at >= self._refresh_seconds:
            self._refresh_queue()

        if not self._heap:
            self._sleep(MAX_SLEEP_SECONDS)
            return

        entry = self._heap[0]
        wait = entry.due_at - time.time()
        if wait > 0:
            self._sleep(min(wait, MAX_SLEEP_SECONDS))
            return  # re-check on next iteration; another region may have queue-jumped

        # Due now (or overdue). Pop and tick.
        heapq.heappop(self._heap)
        self._scheduled_ids.discard(entry.region_id)
        self._tick_and_reschedule(entry.region_id)

    def _tick_and_reschedule(self, region_id: int) -> TickResult | None:
        try:
            result = tick_region(region_id)
        except Exception:
            # tick_region already logged + rolled back. Reschedule with the
            # default interval as a backstop so a single bad tick doesn't
            # wedge the region forever.
            self._reschedule(region_id, fallback=True)
            return None

        if result.skipped:
            log.info(
                "tick region=%s skipped (%s)",
                result.region_id, result.skipped_reason,
            )
        else:
            log.info(
                "tick region=%s name=%r entities=%d events=%d "
                "rels_updated=%d duration_ms=%.1f",
                result.region_id, result.region_name,
                result.entities_loaded, result.events_emitted,
                result.relationships_updated, result.duration_ms,
            )
        self._reschedule(region_id, fallback=False)
        return result

    def _reschedule(self, region_id: int, *, fallback: bool) -> None:
        """Push the region back onto the heap at ``now + interval``.

        Reads the (possibly updated) tick_interval_seconds straight from the
        DB, so an operator can re-tune cadence on the fly. ``fallback=True``
        means we couldn't tick it; use 60s as a safety interval to avoid
        hammering on persistent failures.
        """
        try:
            with get_connection() as conn:
                region = regions_repo.get_region(conn, region_id)
        except Exception:
            log.exception("reschedule lookup failed for region %s", region_id)
            region = None

        if region is None or bool(region["paused"]):
            # Region gone or paused — leave it off the heap; refresh will
            # pick it up again if it comes back.
            return

        interval = 60.0 if fallback else float(region["tick_interval_seconds"])
        due_at = time.time() + interval
        heapq.heappush(self._heap, _HeapEntry(due_at=due_at, region_id=region_id))
        self._scheduled_ids.add(region_id)

    def _sleep(self, seconds: float) -> None:
        """Bounded sleep that wakes promptly on stop()."""
        if seconds <= 0:
            return
        # Polling sleep so SIGINT / stop() is observed within ~0.1s.
        end = time.monotonic() + seconds
        while not self._stopping:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.1))


# ---------- module-level helpers ----------

def run_forever() -> None:
    Scheduler().run_forever()


def _to_aware_utc(dt: datetime) -> datetime:
    """Postgres TIMESTAMPTZ comes back tz-aware; bare datetimes are treated as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

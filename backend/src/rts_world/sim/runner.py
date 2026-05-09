"""CLI entry point for the background simulation.

Usage:

    python -m rts_world.sim.runner once    --region-id N
    python -m rts_world.sim.runner once    --region-name "Whisperwood"
    python -m rts_world.sim.runner forever
    python -m rts_world.sim.runner status
    python -m rts_world.sim.runner seed-regions [--reset] [--regions N] [--max-per-region N]

The shim ``backend/scripts/sim.py`` re-exports ``main()`` for convenience so
you can also invoke it as ``python backend/scripts/sim.py ...`` without
needing PYTHONPATH gymnastics.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Sequence

from ..db.db import get_connection
from . import regions as regions_repo
from .scheduler import Scheduler
from .tick import tick_region


log = logging.getLogger(__name__)


def _resolve_region_id(args: argparse.Namespace) -> int:
    if args.region_id is not None:
        return int(args.region_id)
    if args.region_name is not None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM regions WHERE name = %s", (args.region_name,)
                )
                row = cur.fetchone()
                if row is None:
                    raise SystemExit(f"no region named {args.region_name!r}")
                return int(row[0])
    raise SystemExit("must pass either --region-id or --region-name")


def cmd_once(args: argparse.Namespace) -> int:
    region_id = _resolve_region_id(args)
    result = tick_region(region_id)
    if result.skipped:
        print(f"region={result.region_id} skipped: {result.skipped_reason}")
        return 0
    print(
        f"region={result.region_id} name={result.region_name!r} "
        f"entities={result.entities_loaded} relationships={result.relationships_loaded} "
        f"events={result.events_emitted} rels_updated={result.relationships_updated} "
        f"game_day={result.game_day} game_tick={result.game_tick} "
        f"duration_ms={result.duration_ms:.1f}"
    )
    return 0


def cmd_forever(_args: argparse.Namespace) -> int:
    Scheduler().run_forever()
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, kind, tick_interval_seconds, last_tick_at, paused,
                       (SELECT COUNT(*) FROM entity_zones z WHERE z.region_id = r.id) AS entity_count
                  FROM regions r
                 ORDER BY id
                """
            )
            rows = cur.fetchall()
            cur.execute("SELECT game_day, game_tick FROM world_clock WHERE id = 1")
            clock_row = cur.fetchone()

    if not rows:
        print("no regions defined. run `seed-regions` to create some.")
        return 0

    print(f"{'id':>3}  {'name':<24}  {'kind':<10}  "
          f"{'tick_s':>6}  {'paused':>6}  {'ents':>5}  last_tick_at")
    for r in rows:
        rid, name, kind, tick_s, last_tick_at, paused, ent_count = r
        print(
            f"{rid:>3}  {str(name):<24}  {str(kind):<10}  "
            f"{int(tick_s):>6}  {'Y' if paused else 'N':>6}  "
            f"{int(ent_count):>5}  {last_tick_at}"
        )
    if clock_row is not None:
        print(f"\nworld_clock: game_day={int(clock_row[0])} game_tick={int(clock_row[1])}")
    return 0


def cmd_seed_regions(args: argparse.Namespace) -> int:
    """Create a few regions and round-robin existing entities into them.

    Idempotent: re-running upserts the regions and fills any entity that
    doesn't already have a region_id. Pass ``--reset`` to re-assign every
    entity (useful for shuffling the demo world).
    """
    seed_names: Sequence[tuple[str, str, int]] = (
        ("Whisperwood",     "wilderness", 180),
        ("Ironwatch Hold",  "city",       180),
        ("Mire of Ash",     "wilderness", 240),
    )[: args.regions]

    if not seed_names:
        raise SystemExit("--regions must be >= 1")

    with get_connection() as conn:
        region_ids: list[int] = []
        for name, kind, tick_s in seed_names:
            rid = regions_repo.upsert_region(
                conn, name=name, kind=kind, tick_interval_seconds=tick_s
            )
            region_ids.append(rid)

        with conn.cursor() as cur:
            if args.reset:
                cur.execute(
                    "UPDATE entity_zones SET region_id = NULL WHERE region_id = ANY(%s)",
                    (region_ids,),
                )

            cur.execute(
                """
                SELECT e.id
                  FROM entities e
                  LEFT JOIN entity_zones z ON z.entity_id = e.id
                 WHERE z.region_id IS NULL
                 ORDER BY e.id
                """
            )
            unassigned: list[int] = [int(row[0]) for row in cur.fetchall()]

        cap = args.max_per_region
        per_region: dict[int, int] = {rid: 0 for rid in region_ids}
        # Pre-compute id -> name so we can stamp the legacy entity_zones.zone column.
        id_to_name: dict[int, str] = {
            rid: name for (name, _, _), rid in zip(seed_names, region_ids)
        }
        assigned = 0
        for entity_id in unassigned:
            # Pick the least-loaded region, respecting cap.
            candidates = [rid for rid in region_ids if per_region[rid] < cap]
            if not candidates:
                break
            target = min(candidates, key=lambda r: per_region[r])
            regions_repo.assign_entity_to_region(
                conn, entity_id, target, zone_label=id_to_name[target]
            )
            per_region[target] += 1
            assigned += 1

        conn.commit()

    print(f"upserted {len(region_ids)} regions, assigned {assigned} entities:")
    for (name, _, _), rid in zip(seed_names, region_ids):
        print(f"  region_id={rid:<3} name={name!r:<26} entities_assigned={per_region[rid]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rts_world.sim.runner",
        description="Background world simulation runner.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    once = sub.add_parser("once", help="Tick a single region once and exit.")
    once.add_argument("--region-id", type=int)
    once.add_argument("--region-name", type=str)
    once.set_defaults(func=cmd_once)

    forever = sub.add_parser("forever", help="Run the scheduler loop until SIGINT.")
    forever.set_defaults(func=cmd_forever)

    status = sub.add_parser("status", help="Print regions + clock state and exit.")
    status.set_defaults(func=cmd_status)

    seed = sub.add_parser(
        "seed-regions",
        help="Create demo regions and assign existing entities to them.",
    )
    seed.add_argument("--regions", type=int, default=3, help="How many demo regions (1-3).")
    seed.add_argument(
        "--max-per-region", type=int, default=300,
        help="Cap on entities per region (roadmap §2 hard cap).",
    )
    seed.add_argument(
        "--reset", action="store_true",
        help="Clear region_id on existing entities before re-assigning.",
    )
    seed.set_defaults(func=cmd_seed_regions)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

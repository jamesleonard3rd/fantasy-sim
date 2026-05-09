"""Print a few randomly generated entities to sanity-check the data layer.

Useful for verifying that names, traits, and magic data load correctly from
`game_data/`. Does not write to the database.

Usage:
    python backend/scripts/demo_generate.py [--count N] [--race RACE]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from src.rts_world.db.entities import (  # noqa: E402
    get_random_magic,
    get_random_name,
    get_starting_traits,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sample entities for inspection.")
    parser.add_argument("--count", type=int, default=5, help="How many entities to print.")
    parser.add_argument("--race", default="Human", help="Race to use for all generated entities.")
    args = parser.parse_args()

    for _ in range(args.count):
        race: str = args.race
        name: str = get_random_name(race)
        magic: dict[str, Any] = get_random_magic(race)
        traits: list[str] = get_starting_traits(race)

        magic_display = magic["available_types"] if magic["available_types"] else ["No magic"]
        trait_display = traits if traits else ["None"]

        print(
            f"Name: {name}, Race: {race}, "
            f"Magic: {', '.join(magic_display)}, "
            f"Traits: {', '.join(trait_display)}"
        )


if __name__ == "__main__":
    main()

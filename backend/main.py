from typing import Any
import src.rts_world.db.db as db
from src.rts_world.db.entities import (
    get_random_magic,
    get_random_race,
    get_random_name,
    get_starting_traits,
)


def main() -> None:
    conn = db.get_connection()

    with conn.cursor():
        for _ in range(5):
            race: str = "Human"
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


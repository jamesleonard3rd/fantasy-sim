from typing import Any
import src.rts_world.db.db as db
from src.rts_world.db.entities import get_random_magic, get_magic_types_available, get_random_race, get_random_name


def main() -> None:
    conn = db.get_connection()

    with conn.cursor() as cur:
        #cur.execute("SELECT * FROM characters;")
        
        #result = cur.fetchall()

        for _ in range(5):
            name: str = get_random_name("High Elf")
            race: str = "High Elf"    #get_random_race()
            magic: dict[str, Any] = get_random_magic("High Elf")
            print(f"Name: {name}, Race: {race}, Magic: {magic["subtype"] if magic["subtype"] else magic["base"]}")


main()
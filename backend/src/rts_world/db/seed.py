
from pathlib import Path
from .db import get_connection
import json
import psycopg


# Get the directory where this script lives
DB_DIR = Path(__file__).parent
PROJECT_DIR = DB_DIR.parent.parent.parent

GAME_DATA = PROJECT_DIR / "game_data"
SCHOOLS = GAME_DATA / "schools"
SCHEMA_FILE = DB_DIR / "schema.sql"
SEED_FILE = DB_DIR / "seed_data.sql"


def run_sql_file(conn: psycopg.Connection, filepath: Path) -> None:
    print(f"Running {filepath.name}...")
    sql = filepath.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"  ✓ {filepath.name} completed")

def add_schools(conn: psycopg.Connection) -> None:
    print("Adding schools...")
    
    for filepath in SCHOOLS.glob("*.json"):
        try:
            content = filepath.read_text()
            data = json.loads(content)
        except FileNotFoundError:
            print(f"  ⚠ School file not found: {filepath.name}, skipping...")
            continue
        except json.JSONDecodeError as e:
            print(f"  ⚠ Invalid JSON in {filepath.name}: {e}, skipping...")
            continue
        except Exception as e:
            print(f"  ⚠ Error reading {filepath.name}: {e}, skipping...")
            continue
        
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM factions WHERE name = %s",
                (data["faction_name"],)
            )
            row = cur.fetchone()
            if not row:
                print(f"  ⚠ Faction '{data['faction_name']}' not found, skipping {filepath.name}")
                continue
            faction_id = row[0]
            
            cur.execute(
                """
                INSERT INTO schools (
                    faction_id, prestige, capacity,
                    min_enrollment_age, max_enrollment_age, enrollment_length,
                    term_start_doy, term_end_doy, application_deadline_doy,
                    entry_requirements
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (faction_id) DO NOTHING
                """,
                (
                    faction_id,
                    data["prestige"],
                    data.get("capacity"),
                    data.get("min_enrollment_age"),
                    data.get("max_enrollment_age"),
                    data.get("enrollment_length"),
                    data["term_start_doy"],
                    data["term_end_doy"],
                    data["application_deadline_doy"],
                    json.dumps(data.get("entry_requirements")) if data.get("entry_requirements") else None
                )
            )
            print(f"  ✓ {data['faction_name']}")
    
    conn.commit()


def seed_database() -> None:
    conn = get_connection()
    
    try:
        run_sql_file(conn, SCHEMA_FILE)
        run_sql_file(conn, SEED_FILE)
        add_schools(conn)
        
        print("\n✓ Database seeded successfully!")


        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        conn.rollback()
        raise
        
    finally:
        conn.close()


if __name__ == "__main__":
    seed_database()


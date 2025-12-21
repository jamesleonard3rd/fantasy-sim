"""
Utility script to load the database schema and optional seed data.
"""
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "src" / "rts_world" / "db" / "schema.sql"
SEED_PATH = BASE_DIR / "src" / "rts_world" / "db" / "seed_data.sql"


def _load_env() -> None:
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def get_dsn(overrides: str | None = None) -> str:
    _load_env()
    return overrides or os.getenv("DATABASE_URL", "postgresql://localhost:5432/rts_world")


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    sql = path.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)


def apply_schema_and_seeds(run_seed: bool = True, dsn: str | None = None) -> None:
    target_dsn = get_dsn(dsn)
    with psycopg.connect(target_dsn, autocommit=True) as conn:
        run_sql_file(conn, SCHEMA_PATH)
        if run_seed:
            run_sql_file(conn, SEED_PATH)
    print(f"Applied schema{' and seeds' if run_seed else ''} to {target_dsn}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Initialize RTS World database.")
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Apply schema only and skip seed data.",
    )
    parser.add_argument(
        "--dsn",
        help="Optional PostgreSQL DSN. Falls back to DATABASE_URL or local default.",
    )
    args = parser.parse_args()

    apply_schema_and_seeds(run_seed=not args.skip_seed, dsn=args.dsn)


if __name__ == "__main__":
    main()

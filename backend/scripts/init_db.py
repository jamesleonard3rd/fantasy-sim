"""
Initialize the RTS World database:

1. Apply the schema (schema.sql).
2. Seed all lookup tables from JSON files under <repo>/game_data.

This delegates to `rts_world.db.seed` so there is one source of truth for
how data is loaded.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = BASE_DIR / "backend"
SCHEMA_PATH = BACKEND_DIR / "src" / "rts_world" / "db" / "schema.sql"


def _load_env() -> None:
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def get_dsn(overrides: str | None = None) -> str:
    _load_env()
    return overrides or os.getenv(
        "DATABASE_URL", "postgresql://localhost:5432/rts_world"
    )


def apply_schema(dsn: str | None = None) -> None:
    target_dsn = get_dsn(dsn)
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with psycopg.connect(target_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print(f"Applied schema to {target_dsn}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize RTS World database.")
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Apply schema only and skip JSON seed loading.",
    )
    parser.add_argument(
        "--dsn",
        help="Optional PostgreSQL DSN. Falls back to DATABASE_URL or local default.",
    )
    args = parser.parse_args()

    if args.skip_seed:
        apply_schema(args.dsn)
        return

    # Make `from src.rts_world...` importable when running this as a script
    # (mirrors how the rest of the backend is laid out).
    sys.path.insert(0, str(BACKEND_DIR))
    from src.rts_world.db.seed import seed_database  # noqa: E402

    seed_database(apply_schema=True)


if __name__ == "__main__":
    main()

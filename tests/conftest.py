"""Pytest configuration: make backend/src importable and provide DB fixtures.

These integration tests run against a real Postgres (the same DB configured
via .env / DATABASE_URL). Tests skip cleanly if the DB is unreachable so
contributors without a local Postgres can still run the rest of the suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "backend" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture(scope="session")
def db_conn():
    """Yield a session-wide psycopg connection, or skip the test if unreachable."""
    try:
        from rts_world.db.db import get_connection  # noqa: WPS433 - intentional late import
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"could not import db module: {e}")

    try:
        conn = get_connection()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"database unreachable: {e}")

    try:
        yield conn
    finally:
        conn.close()

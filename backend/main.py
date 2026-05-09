"""Backend CLI entry point.

Currently supports a single subcommand:

    python backend/main.py ping [--dsn DSN]

Pings the configured Postgres database to verify connectivity.
"""
from __future__ import annotations

import argparse
import sys

import psycopg

from src.rts_world.db.db import get_connection


def cmd_ping(args: argparse.Namespace) -> int:
    try:
        if args.dsn:
            conn = psycopg.connect(args.dsn)
        else:
            conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
                assert row is not None and row[0] == 1
        print("OK database reachable")
        return 0
    except Exception as e:
        print(f"ERROR cannot reach database: {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backend", description="RTS World backend CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    ping = sub.add_parser("ping", help="Verify database connectivity.")
    ping.add_argument("--dsn", help="Optional Postgres DSN; otherwise uses .env settings.")
    ping.set_defaults(func=cmd_ping)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

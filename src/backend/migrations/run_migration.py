#!/usr/bin/env python3
"""
DrugTree Database Migration Runner

Runs SQL migrations against the SQLite database.
Follows simple migration pattern: each file runs once, tracked in migrations table.
"""

import argparse
import sqlite3
from pathlib import Path
from typing import List


MIGRATIONS_DIR = Path(__file__).parent


def get_applied_migrations(conn: sqlite3.Connection) -> set:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='migrations'"
    )
    if not cur.fetchone():
        conn.execute(
            """
            CREATE TABLE migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        return set()

    cur = conn.execute("SELECT filename FROM migrations")
    return {row[0] for row in cur.fetchall()}


def get_pending_migrations(applied: set) -> List[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in files if f.name not in applied]


def run_migration(conn: sqlite3.Connection, migration_file: Path) -> None:
    sql = migration_file.read_text()
    conn.executescript(sql)
    conn.execute(
        "INSERT INTO migrations (filename) VALUES (?)",
        (migration_file.name,),
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--db",
        default="drugtree.db",
        help="SQLite database file (default: drugtree.db)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List pending migrations without running",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    applied = get_applied_migrations(conn)
    pending = get_pending_migrations(applied)

    if not pending:
        print("No pending migrations")
        conn.close()
        return

    if args.list:
        print("Pending migrations:")
        for f in pending:
            print(f"  - {f.name}")
        conn.close()
        return

    for migration_file in pending:
        print(f"Running: {migration_file.name}")
        run_migration(conn, migration_file)
        print(f"  ✓ Applied")

    print(f"\nCompleted {len(pending)} migration(s)")
    conn.close()


if __name__ == "__main__":
    main()

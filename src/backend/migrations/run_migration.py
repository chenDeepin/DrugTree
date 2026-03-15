#!/usr/bin/env python3
"""
DrugTree Database Migration Runner

Runs SQL migrations against PostgreSQL (or SQLite as fallback).
Follows simple migration pattern: each file runs once, tracked in migrations table.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Set

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import DatabaseConnection, get_db, close_db


MIGRATIONS_DIR = Path(__file__).parent


async def get_applied_migrations(db: DatabaseConnection) -> Set[str]:
    """
    Get set of already applied migration filenames

    Args:
        db: Database connection

    Returns:
        Set of applied migration filenames
    """
    try:
        if db.is_postgres:
            rows = await db.fetch("SELECT filename FROM migrations ORDER BY filename")
            return {row["filename"] for row in rows}
        else:
            rows = await db.fetch("SELECT filename FROM migrations")
            return {row[0] for row in rows}
    except Exception:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS migrations (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        return set()


def get_pending_migrations(applied: Set[str]) -> List[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in files if f.name not in applied]


async def run_migration(db: DatabaseConnection, migration_file: Path) -> None:
    sql = migration_file.read_text()
    await db.execute(sql)
    await db.execute(
        "INSERT INTO migrations (filename) VALUES ($1)", (migration_file.name,)
    )
    print(f"  ✓ Applied {migration_file.name}")


async def main():
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List pending migrations without running",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )
    args = parser.parse_args()

    db = await get_db()

    try:
        applied = await get_applied_migrations(db)
        pending = get_pending_migrations(applied)

        if not pending:
            print("No pending migrations")
            return

        if args.list:
            print("Pending migrations:")
            for f in pending:
                print(f"  - {f.name}")
            return

        print(f"Found {len(pending)} pending migration(s)")
        print(f"Database type: {'PostgreSQL' if db.is_postgres else 'SQLite'}")
        print()

        for migration_file in pending:
            print(f"Running: {migration_file.name}")
            await run_migration(db, migration_file)

        print(f"\n✓ Completed {len(pending)} migration(s)")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())

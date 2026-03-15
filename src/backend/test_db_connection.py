#!/usr/bin/env python3
"""Test database connection"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from db.connection import get_db, close_db


async def test_connection():
    try:
        print("Testing database connection...")
        db = await get_db()

        db_type = "PostgreSQL" if db.is_postgres else "SQLite"
        print(f"Connected to: {db_type}")

        result = await db.fetch("SELECT 1 as test")
        print(f"Test query result: {result}")

        await close_db()
        print("✓ Database connection test PASSED")
        return True
    except Exception as e:
        print(f"✗ Database connection test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)

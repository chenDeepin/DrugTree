#!/usr/bin/env python3
"""Test database connection directly"""

import sys

sys.path.insert(0, ".")

from db.connection import get_connection

conn = get_connection()
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("✅ Database connection successful!")
print(f"Tables: {cursor.fetchall()}")
cursor.close()
conn.close()

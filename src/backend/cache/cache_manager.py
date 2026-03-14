"""
DrugTree - SQLite Cache Manager

Provides a simple SQLite-based cache with TTL support for API response caching.
Designed for single-server deployment (v1 scope).
"""

import gzip
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional


class CacheManager:
    """
    SQLite-based cache with TTL and optional gzip compression.

    Usage:
        cache = CacheManager()
        cache.set("chembl:drug:CHEMBL1485", {"name": "aspirin"}, ttl=86400)
        data = cache.get("chembl:drug:CHEMBL1485")
    """

    DEFAULT_DB_PATH = Path(__file__).parent / "api_cache.db"
    DEFAULT_TTL = 86400  # 24 hours

    def __init__(self, db_path: Optional[Path] = None, compress_threshold: int = 1024):
        """
        Initialize cache manager.

        Args:
            db_path: Path to SQLite database file
            compress_threshold: Compress values larger than this (bytes)
        """
        self.db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        self.compress_threshold = compress_threshold
        self._init_db()

    def _init_db(self) -> None:
        """Create cache table if not exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    ttl INTEGER NOT NULL,
                    compressed INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at ON cache(created_at)
            """)
            conn.commit()

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve cached value.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/missing
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value, created_at, ttl, compressed FROM cache WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            value_blob, created_at, ttl, compressed = row

            # Check TTL
            if time.time() - created_at > ttl:
                self.delete(key)
                return None

            # Decompress if needed
            if compressed:
                value_blob = gzip.decompress(value_blob)

            return json.loads(value_blob.decode("utf-8"))

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Store value in cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl: Time-to-live in seconds (default: 24h)
        """
        ttl = ttl if ttl is not None else self.DEFAULT_TTL
        value_json = json.dumps(value).encode("utf-8")

        # Compress if large
        compressed = 0
        if len(value_json) > self.compress_threshold:
            value_blob = gzip.compress(value_json)
            compressed = 1
        else:
            value_blob = value_json

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache (key, value, created_at, ttl, compressed)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key, value_blob, time.time(), ttl, compressed),
            )
            conn.commit()

    def delete(self, key: str) -> None:
        """Delete cached value."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()

    def clear(self) -> None:
        """Clear all cached values."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cache")
            conn.commit()

    def clear_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM cache WHERE created_at + ttl < ?", (time.time(),)
            )
            conn.commit()
            return cursor.rowcount

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with total_entries, total_size_bytes, expired_entries
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM cache")
            total_entries = cursor.fetchone()[0]

            cursor = conn.execute("SELECT SUM(LENGTH(value)) FROM cache")
            total_size = cursor.fetchone()[0] or 0

            cursor = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE created_at + ttl < ?", (time.time(),)
            )
            expired_entries = cursor.fetchone()[0]

            return {
                "total_entries": total_entries,
                "total_size_bytes": total_size,
                "expired_entries": expired_entries,
            }


# Singleton instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get or create singleton cache manager."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager

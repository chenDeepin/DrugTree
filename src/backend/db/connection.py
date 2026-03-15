"""
Database Connection Module for DrugTree

Provides async PostgreSQL connection pooling with:
- Automatic connection management
- Environment-based configuration
- Context manager support
- Graceful degradation to SQLite for development
"""

import asyncio
import logging
import os
from typing import Optional, AsyncGenerator, Any
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Try to import asyncpg, fall back to SQLite if not available
try:
    import asyncpg

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    logger.warning("asyncpg not available, falling back to SQLite")

try:
    import aiosqlite

    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False


class DatabaseConnectionError(Exception):
    """Raised when database connection fails"""

    pass


class DatabaseConnection:
    """
    Async database connection manager with connection pooling

    Usage:
        db = DatabaseConnection()
        await db.connect()
        async with db.get_connection() as conn:
            result = await conn.fetch("SELECT * FROM drugs")
        await db.disconnect()

    Or as async context manager:
        async with DatabaseConnection() as db:
            async with db.get_connection() as conn:
                result = await conn.fetch("SELECT * FROM drugs")
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        pool_size: int = 10,
        min_pool_size: int = 5,
        max_pool_size: int = 20,
    ):
        """
        Initialize database connection manager

        Args:
            database_url: PostgreSQL connection URL (falls back to DATABASE_url env var)
            pool_size: Initial pool size (PostgreSQL only)
            min_pool_size: Minimum pool size (PostgreSQL only)
            max_pool_size: Maximum pool size (PostgreSQL only)
        """
        self.database_url = database_url or os.getenv("DATABASE_url")
        self.pool_size = pool_size
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size

        self._pool = None
        self._sqlite_conn = None
        self._is_postgres = False

    async def connect(self) -> None:
        """Establish database connection pool"""
        if self._pool is not None or self._sqlite_conn is not None:
            return

        if self.database_url and POSTGRES_AVAILABLE:
            try:
                self._pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=self.min_pool_size,
                    max_size=self.max_pool_size,
                )
                self._is_postgres = True
                logger.info(
                    f"Connected to PostgreSQL (pool size: {self.min_pool_size}-{self.max_pool_size})"
                )
            except Exception as e:
                logger.error(f"Failed to connect to PostgreSQL: {e}")
                if not SQLITE_AVAILABLE:
                    raise DatabaseConnectionError(
                        f"Failed to connect to PostgreSQL and SQLite not available: {e}"
                    )
                logger.warning("Falling back to SQLite")
                self._is_postgres = False
        else:
            if self.database_url:
                logger.warning("asyncpg not available, falling back to SQLite")
            self._is_postgres = False

        if not self._is_postgres:
            if not SQLITE_AVAILABLE:
                raise DatabaseConnectionError("Neither asyncpg nor aiosqlite available")
            self._sqlite_conn = await aiosqlite.connect("drugtree.db")
            logger.info("Connected to SQLite database (drugtree.db)")

    async def disconnect(self) -> None:
        """Close database connection pool"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Disconnected from PostgreSQL")

        if self._sqlite_conn:
            await self._sqlite_conn.close()
            self._sqlite_conn = None
            logger.info("Disconnected from SQLite")

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator:
        """
        Get a database connection from the pool

        Yields:
            asyncpg.Connection or aiosqlite.Connection

        Usage:
            async with db.get_connection() as conn:
                result = await conn.fetch("SELECT * FROM drugs")
        """
        if self._pool is None and self._sqlite_conn is None:
            await self.connect()

        if self._is_postgres and self._pool:
            async with self._pool.acquire() as conn:
                yield conn
        elif self._sqlite_conn:
            yield self._sqlite_conn
        else:
            raise DatabaseConnectionError("No database connection available")

    @asynccontextmanager
    async def transaction(self):
        """
        Get a connection with transaction management

        Usage:
            async with db.transaction() as conn:
                await conn.execute("INSERT INTO drugs ...")
                await conn.execute("INSERT INTO atc_codes ...")
                # Auto-commits on exit, rolls back on exception
        """
        async with self.get_connection() as conn:
            if self._is_postgres:
                async with conn.transaction():
                    yield conn
            else:
                # SQLite: manual transaction
                await conn.execute("BEGIN")
                try:
                    yield conn
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise

    async def execute(self, query: str, *args) -> None:
        """Execute a query without returning results"""
        async with self.get_connection() as conn:
            await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list:
        """Execute a query and return all results"""
        async with self.get_connection() as conn:
            if self._is_postgres:
                return await conn.fetch(query, *args)
            else:
                # SQLite returns list of tuples, convert to dict-like rows
                cursor = await conn.execute(query, args)
                rows = await cursor.fetchall()
                return rows

    async def fetchrow(self, query: str, *args) -> Optional[tuple]:
        """Execute a query and return single row"""
        async with self.get_connection() as conn:
            if self._is_postgres:
                return await conn.fetchrow(query, *args)
            else:
                cursor = await conn.execute(query, args)
                return await cursor.fetchone()

    async def fetchval(self, query: str, *args) -> Optional[Any]:
        """Execute a query and return single value"""
        row = await self.fetchrow(query, *args)
        return row[0] if row else None

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL backend"""
        return self._is_postgres

    @property
    def is_connected(self) -> bool:
        """Check if connection is established"""
        return self._pool is not None or self._sqlite_conn is not None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()


# Global connection instance (singleton pattern)
_db: Optional[DatabaseConnection] = None


async def get_db() -> DatabaseConnection:
    """
    Get or create global database connection

    Usage:
        db = await get_db()
        result = await db.fetch("SELECT * FROM drugs")
    """
    global _db
    if _db is None:
        _db = DatabaseConnection()
        await _db.connect()
    return _db


async def close_db() -> None:
    """Close global database connection"""
    global _db
    if _db is not None:
        await _db.disconnect()
        _db = None

"""Test helper: treat a single asyncpg connection as a one-slot pool."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg


class ConnectionPoolShim:
    """Minimal asyncpg.Pool stand-in backed by one connection."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        yield self._conn

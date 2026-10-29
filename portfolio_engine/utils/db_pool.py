import os
from pathlib import Path
from typing import Optional

import asyncpg
from dotenv import load_dotenv

ENGINE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ENGINE_DIR / ".env")
load_dotenv(ENGINE_DIR.parent / ".env")


class AsyncDatabasePool:
    _instance: Optional["AsyncDatabasePool"] = None

    def __new__(cls) -> "AsyncDatabasePool":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.pool = None
        return cls._instance

    async def connect(self) -> asyncpg.Pool:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=os.getenv("DB_HOST", "127.0.0.1"),
                port=int(os.getenv("DB_PORT", "5432")),
                database=os.getenv("DB_NAME", "investor_db"),
                user=os.getenv("DB_USER", "investor_app"),
                password=os.getenv("DB_PASSWORD", ""),
                min_size=1,
                max_size=10,
                command_timeout=60,
            )
        return self.pool

    async def get_pool(self) -> asyncpg.Pool:
        return await self.connect()

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None


db_pool = AsyncDatabasePool()

"""
config/database.py
──────────────────
Async MongoDB connection manager using Motor.
Provides a single shared client and database handle.
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from .settings import get_settings
import logging

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    global _client, _database
    settings = get_settings()
    logger.info("Connecting to MongoDB…")
    _client = AsyncIOMotorClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=30000,
        connectTimeoutMS=30000,
        socketTimeoutMS=30000,
    )
    _database = _client[settings.db_name]
    # Ping to confirm connection
    await _database.command("ping")
    logger.info(f"✅ Connected to MongoDB → database: '{settings.db_name}'")


async def disconnect_db() -> None:
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB connection closed.")


def get_db() -> AsyncIOMotorDatabase:
    if _database is None:
        raise RuntimeError("Database not connected. Call connect_db() first.")
    return _database

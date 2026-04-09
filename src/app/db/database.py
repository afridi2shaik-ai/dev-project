from typing import ClassVar

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings


class MongoClient:
    _clients: ClassVar[dict[str, AsyncIOMotorClient]] = {}

    @classmethod
    def get_client(cls, alias: str = "default") -> AsyncIOMotorClient:
        if alias not in cls._clients:
            cls._clients[alias] = AsyncIOMotorClient(settings.MONGO_URI)
        return cls._clients[alias]

    @classmethod
    def close_clients(cls):
        for client in cls._clients.values():
            client.close()
        cls._clients.clear()


def get_database(tenant_id: str, client: AsyncIOMotorClient = None) -> AsyncIOMotorDatabase:
    if client is None:
        client = MongoClient.get_client()
    return client[tenant_id]


def get_global_database(client: AsyncIOMotorClient = None) -> AsyncIOMotorDatabase:
    """Returns the application's global, shared database client."""
    if client is None:
        client = MongoClient.get_client()
    return client[settings.MONGO_GLOBAL_DB]
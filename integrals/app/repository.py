"""
Base de datos del servicio.
"""
from typing import Any, Optional
from pymongo.errors import DuplicateKeyError

class DuplicateIntegral(Exception):
    pass

class IntegralRepository:
    def __init__(self, database):
        self.integrals = database.integrals
        self.identity = database.bot_identity

    def insert(self, integral: dict[str, Any]) -> None:
        try:
            self.integrals.insert_one({**integral, "_id": integral["id"]})
        except DuplicateKeyError:
            raise DuplicateIntegral(integral["id"])

    def get(self, integral_id: str) -> Optional[dict[str, Any]]:
        return self.integrals.find_one({"_id": integral_id}, {"_id": 0})

    def list(self, limit: int, offset: int,
             status: Optional[str] = None) -> tuple[list[dict[str, Any]], int]:
        query = {"status": status} if status else {}
        items = self.integrals.find(query, {"_id": 0}).sort("created_at", -1)
        return list(items.skip(offset).limit(limit)), self.integrals.count_documents(query)

    def get_bot_id(self) -> Optional[str]:
        record = self.identity.find_one({"_id": "bot"})
        return record["user_id"] if record else None

    def set_bot_id(self, user_id: str) -> None:
        self.identity.replace_one({"_id": "bot"}, {"_id": "bot", "user_id": user_id},
                                  upsert=True)

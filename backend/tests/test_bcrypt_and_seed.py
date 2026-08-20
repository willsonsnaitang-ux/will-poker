"""Password hash storage format + admin seeding (direct DB inspection)."""
import asyncio
import os
from pathlib import Path

from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

# Load the project's backend/.env regardless of where pytest is executed.
BACKEND_DIR = Path(__file__).resolve().parents[1]
env = dotenv_values(BACKEND_DIR / ".env")

MONGO_URL = os.environ.get("MONGO_URL") or env.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or env.get("DB_NAME")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _get_admin():
    client = AsyncIOMotorClient(MONGO_URL)
    try:
        return await client[DB_NAME].users.find_one({"role": "admin"}, {"_id": 0})
    finally:
        client.close()


def test_admin_seeded_with_bcrypt_2b_hash():
    admin = _run(_get_admin())
    assert admin is not None, "admin user not seeded"
    h = admin["password_hash"]
    assert h.startswith("$2b$"), f"hash is not bcrypt $2b$ format: {h[:10]}"
    assert len(h) == 60
    assert admin["role"] == "admin"
    assert admin["bankroll"] > 0

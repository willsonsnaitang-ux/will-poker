import os
import re
import sys
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

# make backend importable for engine unit tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

frontend_env = dotenv_values(Path(__file__).resolve().parents[2] / "frontend" / ".env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
BASE_URL = _base.rstrip("/") if _base else None


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def test_credentials():
    p = Path(__file__).resolve().parents[2] / "memory" / "test_credentials.md"
    if not p.exists():
        pytest.skip("missing test_credentials.md")
    c = p.read_text(encoding="utf-8")
    e = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?email(?:\*\*)?\s*:\s*`?([^`\s]+)', c)
    pw = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)', c)
    if not e or not pw:
        pytest.skip("no credentials found")
    return {"email": e.group(1), "password": pw.group(1)}


@pytest.fixture
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def admin_client(api_client, test_credentials):
    r = api_client.post(f"{BASE_URL}/api/auth/login", json=test_credentials, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    return api_client


def register_user(session=None, prefix="TEST_"):
    """Register a fresh throwaway user; returns (session, user_json, payload)."""
    s = session or requests.Session()
    uid = uuid.uuid4().hex[:8]
    payload = {
        "email": f"test_{uid}@qa-willpoker.com",
        "password": "Passw0rd!",
        "username": f"{prefix}{uid}",
    }
    r = s.post(f"{BASE_URL}/api/auth/register", json=payload, timeout=30)
    assert r.status_code == 200, f"register failed {r.status_code}: {r.text[:300]}"
    return s, r.json(), payload


@pytest.fixture
def new_user():
    s, user, payload = register_user()
    return s, user, payload

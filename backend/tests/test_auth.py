"""Auth module: register / login / me / ws-token / refresh / logout."""
import uuid

import pytest
import requests

from conftest import BASE_URL, register_user


class TestRegister:
    def test_register_success_sets_cookies_and_bankroll(self):
        s, user, payload = register_user()
        assert user["email"] == payload["email"]
        assert user["username"] == payload["username"]
        assert user["bankroll"] == 10000
        assert user["role"] == "user"
        assert isinstance(user["id"], str)
        assert "password_hash" not in user
        assert "_id" not in user
        assert "access_token" in s.cookies
        assert "refresh_token" in s.cookies
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert me.status_code == 200
        assert me.json()["id"] == user["id"]

    def test_register_duplicate_email(self):
        s, user, payload = register_user()
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": payload["email"], "password": "Passw0rd!",
            "username": "other" + uuid.uuid4().hex[:6]}, timeout=30)
        assert r.status_code == 400
        assert "already registered" in r.json()["detail"].lower()

    def test_register_duplicate_username(self):
        s, user, payload = register_user()
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"x{uuid.uuid4().hex[:8]}@qa-willpoker.com",
            "password": "Passw0rd!", "username": payload["username"]}, timeout=30)
        assert r.status_code == 400
        assert "taken" in r.json()["detail"].lower()

    def test_register_short_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"s{uuid.uuid4().hex[:8]}@qa-willpoker.com",
            "password": "abc", "username": "short" + uuid.uuid4().hex[:6]}, timeout=30)
        assert r.status_code == 400

    def test_register_invalid_email(self):
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": "notanemail", "password": "Passw0rd!",
            "username": "bad" + uuid.uuid4().hex[:6]}, timeout=30)
        assert r.status_code == 422


class TestLogin:
    def test_admin_login(self, api_client, test_credentials):
        r = api_client.post(f"{BASE_URL}/api/auth/login", json=test_credentials, timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["email"] == test_credentials["email"]
        assert data["role"] == "admin"
        assert "access_token" in api_client.cookies

    def test_login_wrong_password(self, test_credentials):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": test_credentials["email"], "password": "definitelywrong"}, timeout=30)
        assert r.status_code == 401

    def test_login_unknown_email(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "nobody_here@qa-willpoker.com", "password": "whatever"}, timeout=30)
        assert r.status_code == 401

    def test_bruteforce_lockout_after_5_failures(self):
        """Playbook requirement: lockout / rate-limit after 5 failed attempts."""
        s, user, payload = register_user()
        codes = []
        for _ in range(6):
            r = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": payload["email"], "password": "wrong-pass-x"}, timeout=30)
            codes.append(r.status_code)
        assert any(c in (423, 429) for c in codes), (
            f"no lockout/rate-limit after 6 failed logins, got {codes}")


class TestSessionEndpoints:
    def test_me_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 401

    def test_me_with_bearer_header(self, new_user):
        s, user, _ = new_user
        token = s.cookies.get("access_token")
        r = requests.get(f"{BASE_URL}/api/auth/me",
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["id"] == user["id"]

    def test_ws_token(self, new_user):
        s, user, _ = new_user
        r = s.post(f"{BASE_URL}/api/auth/ws-token", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json()["token"], str)
        assert len(r.json()["token"]) > 20

    def test_ws_token_unauthenticated(self):
        r = requests.post(f"{BASE_URL}/api/auth/ws-token", timeout=30)
        assert r.status_code == 401

    def test_refresh(self, new_user):
        s, user, _ = new_user
        r = s.post(f"{BASE_URL}/api/auth/refresh", timeout=30)
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert s.get(f"{BASE_URL}/api/auth/me", timeout=30).status_code == 200

    def test_refresh_without_cookie(self):
        r = requests.post(f"{BASE_URL}/api/auth/refresh", timeout=30)
        assert r.status_code == 401

    def test_invalid_token_rejected(self):
        r = requests.get(f"{BASE_URL}/api/auth/me",
                         headers={"Authorization": "Bearer not.a.jwt"}, timeout=30)
        assert r.status_code == 401

    def test_logout_clears_session(self, new_user):
        s, user, _ = new_user
        r = s.post(f"{BASE_URL}/api/auth/logout", timeout=30)
        assert r.status_code == 200
        r2 = s.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r2.status_code == 401, "session still valid after logout"

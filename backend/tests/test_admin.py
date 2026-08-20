"""Admin endpoints: stats, users, bankroll adjust + RBAC."""
import requests

from conftest import BASE_URL


class TestAdminRBAC:
    def test_stats_requires_auth(self):
        assert requests.get(f"{BASE_URL}/api/admin/stats", timeout=30).status_code == 401

    def test_stats_forbidden_for_normal_user(self, new_user):
        s, _, _ = new_user
        assert s.get(f"{BASE_URL}/api/admin/stats", timeout=30).status_code == 403

    def test_users_forbidden_for_normal_user(self, new_user):
        s, _, _ = new_user
        assert s.get(f"{BASE_URL}/api/admin/users", timeout=30).status_code == 403

    def test_bankroll_forbidden_for_normal_user(self, new_user):
        s, user, _ = new_user
        r = s.post(f"{BASE_URL}/api/admin/bankroll",
                   json={"user_id": user["id"], "delta": 100000, "reason": "hack"}, timeout=30)
        assert r.status_code == 403


class TestAdminEndpoints:
    def test_stats(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/admin/stats", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("users", "hands", "tables", "active_players"):
            assert k in d
            assert isinstance(d[k], int)
        assert d["users"] >= 1
        assert d["tables"] >= 4

    def test_users_list_hides_secrets(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/admin/users", timeout=30)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list)
        assert len(users) >= 1
        for u in users:
            assert "_id" not in u
            assert "password_hash" not in u
            assert "id" in u
            assert "email" in u

    def test_bankroll_adjust_persists(self, admin_client, new_user):
        s, target, _ = new_user
        before = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["bankroll"]
        r = admin_client.post(f"{BASE_URL}/api/admin/bankroll",
                              json={"user_id": target["id"], "delta": 500,
                                    "reason": "TEST_adjust"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        after = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["bankroll"]
        assert after == before + 500
        admin_client.post(f"{BASE_URL}/api/admin/bankroll",
                          json={"user_id": target["id"], "delta": -500,
                                "reason": "TEST_revert"}, timeout=30)
        final = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["bankroll"]
        assert final == before

    def test_bankroll_unknown_user(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/admin/bankroll",
                              json={"user_id": "no-such-user", "delta": 1}, timeout=30)
        assert r.status_code == 404

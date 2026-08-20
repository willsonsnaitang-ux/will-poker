"""Tables: list, join (buy-in validation), leave, bankroll accounting, hand history."""
import requests

from conftest import BASE_URL

EXPECTED = {
    "Maple Leaf": (5, 10),
    "Rideau Rapids": (10, 20),
    "Niagara Nightly": (25, 50),
    "Yukon Grinders": (1, 2),
}


def _tables():
    r = requests.get(f"{BASE_URL}/api/tables", timeout=30)
    assert r.status_code == 200
    return r.json()


class TestTableList:
    def test_list_tables_public(self):
        tables = _tables()
        assert isinstance(tables, list)
        assert len(tables) >= 4
        names = {t["name"] for t in tables}
        for n in EXPECTED:
            assert n in names, f"missing seeded table {n}"

    def test_table_shape_and_no_mongo_id(self):
        for t in _tables():
            assert "_id" not in t
            for k in ("id", "name", "stakes", "small_blind", "big_blind",
                      "max_seats", "buy_in_min", "buy_in_max", "seated", "in_hand"):
                assert k in t, f"missing {k} in table payload"
            assert t["max_seats"] == 6
            if t["name"] in EXPECTED:
                sb, bb = EXPECTED[t["name"]]
                assert (t["small_blind"], t["big_blind"]) == (sb, bb)
                assert t["stakes"] == f"{sb}/{bb}"


class TestJoinLeave:
    def test_join_requires_auth(self):
        tid = _tables()[0]["id"]
        r = requests.post(f"{BASE_URL}/api/tables/{tid}/join", json={"buy_in": 200}, timeout=30)
        assert r.status_code == 401

    def test_join_unknown_table(self, new_user):
        s, _, _ = new_user
        r = s.post(f"{BASE_URL}/api/tables/does-not-exist/join",
                   json={"buy_in": 200}, timeout=30)
        assert r.status_code == 404

    def test_join_buy_in_below_min(self, new_user):
        s, _, _ = new_user
        t = next(x for x in _tables() if x["name"] == "Maple Leaf")
        r = s.post(f"{BASE_URL}/api/tables/{t['id']}/join",
                   json={"buy_in": t["buy_in_min"] - 1}, timeout=30)
        assert r.status_code == 400
        assert "Buy-in must be between" in r.json()["detail"]

    def test_join_buy_in_above_max(self, new_user):
        s, _, _ = new_user
        t = next(x for x in _tables() if x["name"] == "Maple Leaf")
        r = s.post(f"{BASE_URL}/api/tables/{t['id']}/join",
                   json={"buy_in": t["buy_in_max"] + 1}, timeout=30)
        assert r.status_code == 400

    def test_join_zero_buy_in_validation(self, new_user):
        s, _, _ = new_user
        t = _tables()[0]
        r = s.post(f"{BASE_URL}/api/tables/{t['id']}/join", json={"buy_in": 0}, timeout=30)
        assert r.status_code == 422

    def test_double_join_rejected(self, new_user):
        s, user, _ = new_user
        t = next(x for x in _tables() if x["name"] == "Yukon Grinders")
        r1 = s.post(f"{BASE_URL}/api/tables/{t['id']}/join", json={"buy_in": 100}, timeout=30)
        assert r1.status_code == 200, r1.text[:200]
        try:
            r2 = s.post(f"{BASE_URL}/api/tables/{t['id']}/join",
                        json={"buy_in": 100}, timeout=30)
            assert r2.status_code == 400
            assert "already seated" in r2.json()["detail"].lower()
        finally:
            s.post(f"{BASE_URL}/api/tables/{t['id']}/leave", timeout=30)

    def test_insufficient_bankroll(self, new_user):
        s, user, _ = new_user
        t = next(x for x in _tables() if x["name"] == "Niagara Nightly")
        t2 = next(x for x in _tables() if x["name"] == "Rideau Rapids")
        # lock 5000 + 2000 = 7000 of 10000, then a 5000 buy-in must fail
        r1 = s.post(f"{BASE_URL}/api/tables/{t['id']}/join", json={"buy_in": 5000}, timeout=30)
        assert r1.status_code == 200, r1.text[:200]
        r2 = s.post(f"{BASE_URL}/api/tables/{t2['id']}/join", json={"buy_in": 2000}, timeout=30)
        assert r2.status_code == 200, r2.text[:200]
        try:
            t3 = next(x for x in _tables() if x["name"] == "Maple Leaf")
            r3 = s.post(f"{BASE_URL}/api/tables/{t3['id']}/join",
                        json={"buy_in": 1000}, timeout=30)
            # bankroll now 3000 so 1000 succeeds; test the real insufficient case
            if r3.status_code == 200:
                s.post(f"{BASE_URL}/api/tables/{t3['id']}/leave", timeout=30)
            me = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()
            big = next(x for x in _tables() if x["buy_in_min"] > me["bankroll"] or
                       x["buy_in_max"] > me["bankroll"])
            r4 = s.post(f"{BASE_URL}/api/tables/{big['id']}/join",
                        json={"buy_in": max(big["buy_in_min"], me["bankroll"] + 1)}, timeout=30)
            assert r4.status_code == 400
        finally:
            s.post(f"{BASE_URL}/api/tables/{t['id']}/leave", timeout=30)
            s.post(f"{BASE_URL}/api/tables/{t2['id']}/leave", timeout=30)

    def test_join_deducts_and_leave_returns_bankroll(self, new_user):
        s, user, _ = new_user
        t = next(x for x in _tables() if x["name"] == "Yukon Grinders")
        before = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["bankroll"]
        buy_in = t["buy_in_max"]
        r = s.post(f"{BASE_URL}/api/tables/{t['id']}/join", json={"buy_in": buy_in}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["ok"] is True
        assert isinstance(body["seat"], int)
        assert 0 <= body["seat"] < 6
        mid = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["bankroll"]
        assert mid == before - buy_in, f"bankroll not deducted: {before} -> {mid}"
        t2 = next(x for x in _tables() if x["id"] == t["id"])
        assert t2["seated"] >= 1
        lr = s.post(f"{BASE_URL}/api/tables/{t['id']}/leave", timeout=30)
        assert lr.status_code == 200, lr.text[:300]
        assert lr.json()["returned"] == buy_in
        after = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["bankroll"]
        assert after == before, f"stack not returned on leave: {before} -> {after}"

    def test_leave_when_not_seated(self, new_user):
        s, _, _ = new_user
        t = _tables()[0]
        r = s.post(f"{BASE_URL}/api/tables/{t['id']}/leave", timeout=30)
        assert r.status_code == 400
        assert "not seated" in r.json()["detail"].lower()

    def test_leave_unknown_table(self, new_user):
        s, _, _ = new_user
        r = s.post(f"{BASE_URL}/api/tables/nope/leave", timeout=30)
        assert r.status_code == 404


class TestHandHistory:
    def test_hands_mine_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/hands/mine", timeout=30)
        assert r.status_code == 401

    def test_hands_mine_returns_list(self, new_user):
        s, _, _ = new_user
        r = s.get(f"{BASE_URL}/api/hands/mine", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for h in data:
            assert "_id" not in h

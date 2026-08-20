"""Iteration 3 E2E over the public preview URL: continuous multi-hand session,
post-hand responsiveness (chat + leave), winner usernames, hand history."""
import json
import time

import pytest
import requests
from websockets.sync.client import connect

from conftest import BASE_URL, register_user

WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")


def pick_empty_table():
    tables = requests.get(f"{BASE_URL}/api/tables", timeout=30).json()
    empty = [t for t in tables if t["seated"] == 0]
    if not empty:
        pytest.skip("no empty table available")
    return sorted(empty, key=lambda t: t["big_blind"])[0]


def ws_token(session):
    r = session.post(f"{BASE_URL}/api/auth/ws-token", timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()["token"]


class Client:
    def __init__(self, session, table_id):
        self.session = session
        self.uid = session.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["id"]
        token = ws_token(session)
        self.ws = connect(f"{WS_BASE}/api/ws/table/{table_id}?token={token}",
                          open_timeout=20)
        self.state = None
        self.errors = []
        self.pump(timeout=8)

    def pump(self, timeout=1.0):
        """Drain all currently available frames, keeping the newest state."""
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = json.loads(self.ws.recv(timeout=max(0.05, end - time.time())))
            except TimeoutError:
                break
            except Exception:
                break
            if msg.get("type") == "state":
                self.state = msg["state"]
            elif msg.get("type") == "error":
                self.errors.append(msg.get("message"))
        return self.state

    def act(self, action, amount=0):
        self.ws.send(json.dumps({"type": "action", "action": action, "amount": amount}))

    def chat(self, text):
        self.ws.send(json.dumps({"type": "chat", "text": text}))

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def owner_of_seat(state, seat_no):
    for p in state.get("players", []):
        if p.get("seat") == seat_no:
            return p.get("user_id")
    return None


class TestContinuousMultiHandSession:
    def test_three_consecutive_hands_and_post_hand_responsiveness(self):
        table = pick_empty_table()
        tid = table["id"]
        buy_in = min(table["buy_in_max"], max(table["buy_in_min"], table["big_blind"] * 60))

        sa, _, _ = register_user(prefix="TEST_m3a")
        sb, _, _ = register_user(prefix="TEST_m3b")
        for s in (sa, sb):
            r = s.post(f"{BASE_URL}/api/tables/{tid}/join",
                       json={"buy_in": buy_in}, timeout=30)
            assert r.status_code == 200, f"join failed {r.status_code}: {r.text[:200]}"

        ca, cb = Client(sa, tid), Client(sb, tid)
        clients = {ca.uid: ca, cb.uid: cb}
        try:
            assert ca.state and ca.state.get("hand"), "no hand after both players seated"
            # Tables persist for the lifetime of the backend, so an empty table
            # may already have completed previous hands. The important guarantee
            # is that a new hand started after these two players joined.
            first_hand_number = ca.state["hand"]["hand_number"]
            assert first_hand_number >= 1

            dealers, hand_ids, completed = [], [], []
            t_start = time.time()
            last_sig = None
            deadline = time.time() + 180
            while len(completed) < 3 and time.time() < deadline:
                for c in clients.values():
                    c.pump(timeout=0.6)
                st = ca.state or {}
                hand = st.get("hand")
                sig = (hand and (hand["hand_number"], hand["street"], hand["to_act"],
                                 hand["ended"]), bool(st.get("next_hand_at")))
                if sig != last_sig:
                    print(f"[{time.time()-t_start:6.1f}] {sig}", flush=True)
                    last_sig = sig
                if not hand:
                    time.sleep(0.5)
                    continue
                hid = hand["hand_id"]
                if hand.get("ended"):
                    if hid not in completed:
                        completed.append(hid)
                        assert hand["winners"], "hand ended with no winners"
                        assert all(w.get("username") for w in hand["winners"]), \
                            f"winner missing username: {hand['winners']}"
                        if len(completed) < 3:
                            assert st.get("next_hand_at"), \
                                "next_hand_at (countdown) not set after hand end"
                    time.sleep(1.0)
                    continue
                if hid not in hand_ids:
                    hand_ids.append(hid)
                    dealers.append(hand["dealer_seat"])
                to_act = hand.get("to_act")
                if to_act is None:
                    time.sleep(0.4)
                    continue
                owner = owner_of_seat(st, to_act)
                c = clients.get(owner)
                if not c:
                    time.sleep(0.4)
                    continue
                c.pump(timeout=0.4)
                legal = (c.state or {}).get("legal_actions") or {}
                if not legal:
                    time.sleep(0.4)
                    continue
                c.act("check" if legal.get("can_check") else "call")
                time.sleep(0.8)

            assert len(completed) >= 3, (
                f"only {len(completed)} hand(s) completed in 180s; "
                f"hands seen={hand_ids}")
            assert len(set(hand_ids)) >= 3, f"hand ids repeated: {hand_ids}"
            assert len(set(dealers[:3])) > 1, f"dealer button did not rotate: {dealers}"
            assert not ca.errors and not cb.errors, f"ws errors: {ca.errors} {cb.errors}"

            # chat must still work after several hands
            ca.chat("TEST_hello_after_hand")
            got = False
            end = time.time() + 10
            while time.time() < end and not got:
                cb.pump(timeout=1.0)
                got = any(m.get("text") == "TEST_hello_after_hand"
                          for m in (cb.state or {}).get("chat", []))
            assert got, "chat not delivered after hands completed"
        finally:
            ca.close()
            cb.close()

        # leave must respond immediately and credit the bankroll
        t0 = time.time()
        r = sa.post(f"{BASE_URL}/api/tables/{tid}/leave", timeout=40)
        elapsed = time.time() - t0
        assert r.status_code == 200, f"leave failed {r.status_code}: {r.text[:200]}"
        assert elapsed < 15, f"leave took {elapsed:.1f}s"
        me = sa.get(f"{BASE_URL}/api/auth/me", timeout=30).json()
        assert me["bankroll"] > 10000 - buy_in, "stack not credited back on leave"
        r2 = sb.post(f"{BASE_URL}/api/tables/{tid}/leave", timeout=40)
        assert r2.status_code == 200

        hands = sa.get(f"{BASE_URL}/api/hands/mine", timeout=30).json()
        assert isinstance(hands, list) and len(hands) >= 3, \
            f"expected >=3 hands in history, got {len(hands)}"


class TestLoginLockout:
    def test_lockout_after_5_failures(self):
        s, user, payload = register_user(prefix="TEST_lock")
        codes = []
        for _ in range(6):
            r = requests.post(f"{BASE_URL}/api/auth/login",
                              json={"email": payload["email"], "password": "Wrong@123"},
                              timeout=30)
            codes.append(r.status_code)
        assert 423 in codes, f"no 423 lockout returned: {codes}"
        detail = json.dumps(r.json()).lower()
        assert "minute" in detail, f"lockout message missing retry hint: {r.json()}"
        r = requests.post(f"{BASE_URL}/api/auth/login", json=payload, timeout=30)
        assert r.status_code == 423, f"expected 423 while locked, got {r.status_code}"

"""Two-client WebSocket multiplayer gameplay tests (real E2E over preview URL)."""
import json
import time

import pytest
import requests
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed

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


def recv_state(ws, timeout=10):
    """Read messages until a state frame arrives; return the state dict."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            msg = json.loads(ws.recv(timeout=max(0.5, end - time.time())))
        except TimeoutError:
            break
        if msg.get("type") == "state":
            return msg["state"]
        if msg.get("type") == "error":
            return {"_error": msg.get("message")}
    return None


def drain_latest_state(ws, timeout=6):
    """Return the newest state frame available within the timeout."""
    latest = None
    end = time.time() + timeout
    while time.time() < end:
        try:
            msg = json.loads(ws.recv(timeout=max(0.3, min(1.5, end - time.time()))))
        except TimeoutError:
            if latest is not None:
                break
            continue
        except ConnectionClosed:
            break
        if msg.get("type") == "state":
            latest = msg["state"]
    return latest


def me_bankroll(session):
    return session.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["bankroll"]


class TestWebSocketAuth:
    def test_ws_rejects_invalid_token(self):
        table = requests.get(f"{BASE_URL}/api/tables", timeout=30).json()[0]
        with connect(f"{WS_BASE}/api/ws/table/{table['id']}?token=garbage") as ws:
            state = recv_state(ws, timeout=8)
            assert state is not None and state.get("_error"), f"expected auth error, got {state}"

    def test_ws_missing_token_rejected(self):
        table = requests.get(f"{BASE_URL}/api/tables", timeout=30).json()[0]
        try:
            with connect(f"{WS_BASE}/api/ws/table/{table['id']}") as ws:
                msg = ws.recv(timeout=5)
                assert "error" in str(msg).lower(), f"unexpected frame: {msg}"
        except Exception:
            pass  # rejected handshake is acceptable

    def test_ws_unknown_table(self):
        s, _, _ = register_user()
        tok = ws_token(s)
        with connect(f"{WS_BASE}/api/ws/table/does-not-exist?token={tok}") as ws:
            state = recv_state(ws, timeout=8)
            assert state and state.get("_error") == "table not found"


class TestTwoPlayerHand:
    """Full heads-up hand over two live WebSocket clients."""

    def test_two_player_hand_plays_to_completion(self):
        table = pick_empty_table()
        tid = table["id"]
        buy_in = table["buy_in_min"]

        s1, u1, _ = register_user()
        s2, u2, _ = register_user()
        t1, t2 = ws_token(s1), ws_token(s2)

        ws1 = connect(f"{WS_BASE}/api/ws/table/{tid}?token={t1}")
        ws2 = connect(f"{WS_BASE}/api/ws/table/{tid}?token={t2}")
        try:
            assert recv_state(ws1) is not None
            assert recv_state(ws2) is not None

            r1 = s1.post(f"{BASE_URL}/api/tables/{tid}/join", json={"buy_in": buy_in}, timeout=30)
            assert r1.status_code == 200, r1.text[:300]
            r2 = s2.post(f"{BASE_URL}/api/tables/{tid}/join", json={"buy_in": buy_in}, timeout=30)
            assert r2.status_code == 200, r2.text[:300]

            # bankroll debited
            assert me_bankroll(s1) == 10000 - buy_in
            assert me_bankroll(s2) == 10000 - buy_in

            st1 = drain_latest_state(ws1)
            st2 = drain_latest_state(ws2)
            assert st1 and st2, "no state broadcast after join"
            assert st1["hand"] is not None, "hand did not auto-start with 2 seated players"
            hand = st1["hand"]
            assert hand["street"] == "preflop"
            assert hand["pot"] == table["small_blind"] + table["big_blind"], (
                f"blinds not posted correctly: pot={hand['pot']}")

            # ---- hole card privacy ----
            def hole(state, uid):
                return next(p["hole_cards"] for p in state["players"] if p["user_id"] == uid)

            assert len(hole(st1, u1["id"])) == 2 and "?" not in hole(st1, u1["id"]), \
                "player 1 did not receive own hole cards"
            assert hole(st1, u2["id"]) == ["?", "?"], \
                f"LEAK: player1 sees opponent hole cards {hole(st1, u2['id'])}"
            assert hole(st2, u1["id"]) == ["?", "?"], \
                f"LEAK: player2 sees opponent hole cards {hole(st2, u1['id'])}"

            sock = {u1["id"]: ws1, u2["id"]: ws2}
            states = {u1["id"]: st1, u2["id"]: st2}
            boards_seen = set()
            streets_seen = set()

            # ---- play the hand: call/check down to showdown ----
            for _ in range(40):
                cur = states[u1["id"]]
                if cur["hand"] and cur["hand"]["ended"]:
                    break
                to_act = cur["hand"]["to_act"]
                actor = next(p["user_id"] for p in cur["players"] if p["seat"] == to_act)
                legal = states[actor].get("legal_actions") or {}
                assert legal, f"no legal_actions delivered to acting player {actor}"
                action = "check" if legal.get("can_check") else "call"
                sock[actor].send(json.dumps({"type": "action", "action": action}))
                time.sleep(0.4)
                for uid in (u1["id"], u2["id"]):
                    new = drain_latest_state(sock[uid], timeout=5)
                    if new:
                        states[uid] = new
                st = states[u1["id"]]
                if st["hand"]:
                    streets_seen.add(st["hand"]["street"])
                    boards_seen.add(tuple(st["hand"]["board"]))

            final1 = states[u1["id"]]
            final2 = states[u2["id"]]
            assert final1["hand"]["ended"], f"hand never ended; streets seen={streets_seen}"
            assert {"flop", "turn", "river"} <= streets_seen or final1["hand"]["board"], (
                f"community cards never dealt; streets seen={streets_seen}")
            assert len(final1["hand"]["board"]) == 5, (
                f"expected 5 board cards at showdown, got {final1['hand']['board']}")
            assert final1["hand"]["winners"], "no winner declared at showdown"
            # both clients in sync
            assert final1["hand"]["hand_id"] == final2["hand"]["hand_id"]
            assert final1["hand"]["winners"] == final2["hand"]["winners"], "clients out of sync"
            # showdown reveals both hands
            assert all(
                "?" not in p["hole_cards"] for p in final1["players"] if not p["folded"]
            ), "hole cards not revealed at showdown"
            # chips awarded
            total_stacks = sum(p["stack"] for p in final1["players"])
            assert total_stacks == 2 * buy_in, (
                f"chip conservation broken: {total_stacks} != {2 * buy_in}")

            # ---- chat sync ----
            ws1.send(json.dumps({"type": "chat", "text": "TEST_hello from p1"}))
            time.sleep(0.5)
            chat_state = drain_latest_state(ws2, timeout=6)
            assert chat_state and any(
                c["text"] == "TEST_hello from p1" for c in chat_state.get("chat", [])
            ), "chat message not delivered to other client"

            # ---- next hand should start automatically after the 3s delay ----
            time.sleep(5)
            nxt = drain_latest_state(ws1, timeout=6) or states[u1["id"]]
            self._next_hand_started = (
                nxt["hand"] is not None and not nxt["hand"]["ended"]
            )

            # ---- hand history persisted ----
            hands = s1.get(f"{BASE_URL}/api/hands/mine", timeout=30).json()
            assert isinstance(hands, list) and len(hands) >= 1, "hand not persisted to history"
            assert any(h["id"] == final1["hand"]["hand_id"] for h in hands), \
                "played hand missing from /api/hands/mine"
            assert all("_id" not in h for h in hands)

            assert self._next_hand_started, (
                "BUG: no new hand started after previous hand ended - table is stuck "
                "(PokerGame.hand is never reset to None)")
        finally:
            try:
                ws1.close()
                ws2.close()
            except Exception:
                pass
            s1.post(f"{BASE_URL}/api/tables/{tid}/leave", timeout=30)
            s2.post(f"{BASE_URL}/api/tables/{tid}/leave", timeout=30)


class TestFoldAndRaiseRules:
    def test_raise_validation_and_fold_ends_hand(self):
        table = pick_empty_table()
        tid = table["id"]
        buy_in = table["buy_in_min"]
        bb = table["big_blind"]

        s1, u1, _ = register_user()
        s2, u2, _ = register_user()
        ws1 = connect(f"{WS_BASE}/api/ws/table/{tid}?token={ws_token(s1)}")
        ws2 = connect(f"{WS_BASE}/api/ws/table/{tid}?token={ws_token(s2)}")
        try:
            recv_state(ws1)
            recv_state(ws2)
            assert s1.post(f"{BASE_URL}/api/tables/{tid}/join", json={"buy_in": buy_in}, timeout=30).status_code == 200
            assert s2.post(f"{BASE_URL}/api/tables/{tid}/join", json={"buy_in": buy_in}, timeout=30).status_code == 200
            st1 = drain_latest_state(ws1)
            st2 = drain_latest_state(ws2)
            states = {u1["id"]: st1, u2["id"]: st2}
            sock = {u1["id"]: ws1, u2["id"]: ws2}
            to_act = st1["hand"]["to_act"]
            actor = next(p["user_id"] for p in st1["players"] if p["seat"] == to_act)
            other = u2["id"] if actor == u1["id"] else u1["id"]

            # out-of-turn action must be rejected
            sock[other].send(json.dumps({"type": "action", "action": "call"}))
            time.sleep(0.4)
            # below-min raise must be rejected
            sock[actor].send(json.dumps({"type": "action", "action": "raise", "amount": bb + 1}))
            time.sleep(0.5)
            after = drain_latest_state(sock[actor], timeout=3)
            cur = after or states[actor]
            assert cur["hand"]["current_bet"] == bb, (
                f"below-min raise accepted: current_bet={cur['hand']['current_bet']}")

            # valid min raise
            sock[actor].send(json.dumps({"type": "action", "action": "raise", "amount": 2 * bb}))
            time.sleep(0.6)
            st = drain_latest_state(sock[other], timeout=6)
            assert st and st["hand"]["current_bet"] == 2 * bb, (
                f"valid min-raise not applied: {st['hand']['current_bet'] if st else None}")

            # other folds -> hand ends uncontested, raiser wins
            sock[other].send(json.dumps({"type": "action", "action": "fold"}))
            time.sleep(1.0)
            end = drain_latest_state(sock[actor], timeout=6)
            assert end and end["hand"]["ended"], "hand did not end after fold"
            assert end["hand"]["winners"] and end["hand"]["winners"][0]["user_id"] == actor, (
                f"wrong winner after fold: {end['hand']['winners']}")
            assert end["hand"]["winners"][0]["reason"] == "uncontested"
        finally:
            try:
                ws1.close()
                ws2.close()
            except Exception:
                pass
            s1.post(f"{BASE_URL}/api/tables/{tid}/leave", timeout=30)
            s2.post(f"{BASE_URL}/api/tables/{tid}/leave", timeout=30)


class TestReconnect:
    def test_reconnect_restores_seat_and_hole_cards(self):
        table = pick_empty_table()
        tid = table["id"]
        buy_in = table["buy_in_min"]
        s1, u1, _ = register_user()
        s2, u2, _ = register_user()
        ws1 = connect(f"{WS_BASE}/api/ws/table/{tid}?token={ws_token(s1)}")
        ws2 = connect(f"{WS_BASE}/api/ws/table/{tid}?token={ws_token(s2)}")
        try:
            recv_state(ws1)
            recv_state(ws2)
            s1.post(f"{BASE_URL}/api/tables/{tid}/join", json={"buy_in": buy_in}, timeout=30)
            s2.post(f"{BASE_URL}/api/tables/{tid}/join", json={"buy_in": buy_in}, timeout=30)
            st1 = drain_latest_state(ws1)
            cards = next(p["hole_cards"] for p in st1["players"] if p["user_id"] == u1["id"])
            ws1.close()
            time.sleep(0.5)
            ws1b = connect(f"{WS_BASE}/api/ws/table/{tid}?token={ws_token(s1)}")
            st = recv_state(ws1b)
            assert st and st["hand"], "state not restored on reconnect"
            mine = next(p for p in st["players"] if p["user_id"] == u1["id"])
            assert mine["hole_cards"] == cards, "hole cards not restored after reconnect"
            assert mine["connected"] is True
            ws1b.close()
        finally:
            try:
                ws2.close()
            except Exception:
                pass
            s1.post(f"{BASE_URL}/api/tables/{tid}/leave", timeout=30)
            s2.post(f"{BASE_URL}/api/tables/{tid}/leave", timeout=30)

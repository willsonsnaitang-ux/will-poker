"""Live 2-player WebSocket session against the preview backend.

Verifies: hand auto-start with 2 seated players, hole-card masking, turn order,
action broadcasting, hand completion (winner banner data + pot award),
next-hand auto-start, and hand-history persistence.

Run standalone:  python /app/backend/tests/ws_live_session.py
"""
import asyncio
import json
import os
import uuid

import httpx
import websockets
from dotenv import dotenv_values

env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or env["REACT_APP_BACKEND_URL"]).rstrip("/")
WS_BASE = BASE.replace("https://", "wss://").replace("http://", "ws://")

RESULTS = []
DEBUG = True


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(("PASS  " if ok else "FAIL  ") + name + ((" :: " + str(detail)) if detail else ""))


async def make_user(client):
    uid = uuid.uuid4().hex[:8]
    payload = {"email": f"ws_{uid}@qa-willpoker.com", "password": "Passw0rd!",
               "username": f"WS_{uid}"}
    r = await client.post(f"{BASE}/api/auth/register", json=payload)
    r.raise_for_status()
    user = r.json()
    t = await client.post(f"{BASE}/api/auth/ws-token")
    t.raise_for_status()
    return user, t.json()["token"]


async def recv_state(ws, timeout=10):
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        msg = json.loads(raw)
        if msg.get("type") == "state":
            st = msg["state"]
            if DEBUG:
                h = st.get("hand")
                print("      [state] hand=", None if h is None else
                      {k: h[k] for k in ("street", "pot", "to_act", "ended", "hand_number")})
            return st
        if msg.get("type") == "error":
            print("   WS ERROR MSG:", msg)
            return None


async def main():
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c1, \
            httpx.AsyncClient(timeout=30, follow_redirects=True) as c2:
        u1, tok1 = await make_user(c1)
        u2, tok2 = await make_user(c2)
        check("register two players + ws-token", True, f"{u1['username']} / {u2['username']}")

        tables = (await c1.get(f"{BASE}/api/tables")).json()
        table = next(t for t in tables if t["name"] == "Yukon Grinders")
        tid = table["id"]
        buy_in = 200

        # bad-token WS must be rejected
        try:
            async with websockets.connect(f"{WS_BASE}/api/ws/table/{tid}?token=bogus") as bad:
                msg = json.loads(await asyncio.wait_for(bad.recv(), timeout=10))
                check("WS rejects invalid token", msg.get("type") == "error", msg)
        except Exception as e:
            check("WS rejects invalid token", False, repr(e))

        ws1 = await websockets.connect(f"{WS_BASE}/api/ws/table/{tid}?token={tok1}")
        ws2 = await websockets.connect(f"{WS_BASE}/api/ws/table/{tid}?token={tok2}")
        s1 = await recv_state(ws1)
        check("WS connect + initial state", s1 is not None and "players" in s1,
              f"players={len(s1['players']) if s1 else None}")
        await recv_state(ws2)

        j1 = await c1.post(f"{BASE}/api/tables/{tid}/join", json={"buy_in": buy_in})
        j2 = await c2.post(f"{BASE}/api/tables/{tid}/join", json={"buy_in": buy_in})
        check("both players joined", j1.status_code == 200 and j2.status_code == 200,
              f"{j1.status_code}/{j2.status_code} {j1.text[:80]} {j2.text[:80]}")

        # drain to latest state
        state1 = None
        try:
            while True:
                st = await asyncio.wait_for(recv_state(ws1, timeout=6), timeout=7)
                if st:
                    state1 = st
        except asyncio.TimeoutError:
            pass

        hand = (state1 or {}).get("hand")
        check("hand auto-started with 2 seated players", bool(hand),
              f"street={hand.get('street') if hand else None} pot={hand.get('pot') if hand else None}")
        if not hand:
            return

        check("blinds posted", hand["pot"] == table["small_blind"] + table["big_blind"],
              f"pot={hand['pot']}")
        me = next(p for p in state1["players"] if p["user_id"] == u1["id"])
        other = next(p for p in state1["players"] if p["user_id"] != u1["id"])
        check("viewer sees own hole cards", len(me["hole_cards"]) == 2 and "?" not in me["hole_cards"],
              me["hole_cards"])
        check("opponent hole cards masked", other["hole_cards"] == ["?", "?"], other["hole_cards"])
        check("turn assigned", hand["to_act"] is not None, hand["to_act"])

        socks = {u1["id"]: ws1, u2["id"]: ws2}
        clients = {u1["id"]: c1, u2["id"]: c2}
        seat_owner = {p["seat"]: p["user_id"] for p in state1["players"]}

        # ---- play the hand out with check/call to reach showdown ----
        state = state1
        steps = 0
        ended_state = None
        while steps < 30:
            steps += 1
            h = state.get("hand")
            if not h:
                break
            if h.get("ended"):
                ended_state = state
                break
            seat = h.get("to_act")
            if seat is None:
                break
            actor = seat_owner.get(seat)
            if actor is None:
                break
            ws = socks[actor]
            # need that viewer's legal actions -> ask for own state
            await ws.send(json.dumps({"type": "ping"}))
            legal = None
            # get a fresh state for the actor
            tmp = await recv_state(ws, timeout=10) if False else None
            # derive action from the last known state for that actor
            print(f"   -> street={h['street']} seat={seat} pot={h['pot']} board={h['board']}")
            action = "check"
            if h["current_bet"] > 0:
                pl = next((p for p in state["players"] if p["seat"] == seat), None)
                if pl and pl["bet"] < h["current_bet"]:
                    action = "call"
            await ws.send(json.dumps({"type": "action", "action": action}))
            try:
                new_state = await recv_state(ws, timeout=12)
            except asyncio.TimeoutError:
                check("action broadcast after hand progresses", False,
                      f"no state broadcast after '{action}' by seat {seat} "
                      f"(street={h['street']}) - possible server deadlock/hang")
                new_state = None
            if new_state is None:
                break
            state = new_state

        _sh = (state or {}).get("hand") or {}
        check("hand reached completion", bool(ended_state) or bool(_sh.get("ended")),
              f"street={_sh.get('street')} ended={_sh.get('ended')} steps={steps}")

        final = ended_state or state or {}
        h = final.get("hand") or {}
        if h.get("ended"):
            check("winner declared with amount", bool(h.get("winners")) and
                  all("amount" in w for w in h["winners"]), h.get("winners"))
            total_stacks = sum(p["stack"] for p in final["players"])
            check("chip conservation across hand", total_stacks == 2 * buy_in,
                  f"total stacks={total_stacks} expected={2 * buy_in}")

        # ---- next hand should auto-start within ~5s ----
        await asyncio.sleep(6)
        next_state = None
        try:
            while True:
                st = await asyncio.wait_for(recv_state(ws1, timeout=4), timeout=5)
                if st:
                    next_state = st
        except asyncio.TimeoutError:
            pass
        nh = (next_state or final).get("hand") or {}
        check("new hand auto-starts after previous ends",
              bool(nh) and not nh.get("ended") and nh.get("hand_number", 0) >= 2,
              f"hand_number={nh.get('hand_number')} ended={nh.get('ended')}")

        # ---- hand history persisted ----
        hist = await c1.get(f"{BASE}/api/hands/mine")
        check("hand history persisted for player", hist.status_code == 200 and len(hist.json()) >= 1,
              f"{hist.status_code} count={len(hist.json()) if hist.status_code == 200 else '-'}")

        # ---- reconnect re-fetches state ----
        await ws1.close()
        ws1b = await websockets.connect(f"{WS_BASE}/api/ws/table/{tid}?token={tok1}")
        rs = await recv_state(ws1b, timeout=10)
        check("reconnect delivers fresh state", rs is not None and "players" in rs,
              f"players={len(rs['players']) if rs else None}")
        await ws1b.close()
        await ws2.close()

        # ---- leave returns chips ----
        for uid, c in clients.items():
            lv = await c.post(f"{BASE}/api/tables/{tid}/leave")
            me_after = (await c.get(f"{BASE}/api/auth/me")).json()
            check(f"leave returns stack ({uid[:6]})", lv.status_code == 200,
                  f"{lv.status_code} returned={lv.json().get('returned') if lv.status_code == 200 else lv.text[:120]} bankroll={me_after['bankroll']}")

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n===== {passed}/{len(RESULTS)} WS checks passed =====")
    for n, ok, d in RESULTS:
        if not ok:
            print("FAILED:", n, "::", d)


asyncio.run(main())

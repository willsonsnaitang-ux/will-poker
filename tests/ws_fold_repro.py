"""Reproduce: does the server broadcast/respond after a hand ends via a WS action?

Two players sit heads-up, the first actor folds -> the hand should end,
winner should be broadcast, and a new hand should start ~3s later.
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


async def make_user(client):
    uid = uuid.uuid4().hex[:8]
    r = await client.post(f"{BASE}/api/auth/register", json={
        "email": f"fold_{uid}@qa-willpoker.com", "password": "Passw0rd!",
        "username": f"FOLD_{uid}"})
    r.raise_for_status()
    t = await client.post(f"{BASE}/api/auth/ws-token")
    return r.json(), t.json()["token"]


async def recv_state(ws, timeout=8):
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        if msg.get("type") == "state":
            return msg["state"]
        print("   msg:", msg)


async def drain(ws, timeout=4):
    last = None
    try:
        while True:
            last = await asyncio.wait_for(recv_state(ws, timeout=timeout), timeout=timeout + 1)
    except asyncio.TimeoutError:
        pass
    return last


async def main():
    async with httpx.AsyncClient(timeout=30) as c1, httpx.AsyncClient(timeout=30) as c2:
        u1, t1 = await make_user(c1)
        u2, t2 = await make_user(c2)
        tables = (await c1.get(f"{BASE}/api/tables")).json()
        # pick a table with no seated players and no stale hand
        table = next((t for t in tables if t["seated"] == 0), tables[0])
        tid = table["id"]
        print("table:", table["name"], "seated:", table["seated"], "in_hand:", table["in_hand"])

        ws1 = await websockets.connect(f"{WS_BASE}/api/ws/table/{tid}?token={t1}")
        ws2 = await websockets.connect(f"{WS_BASE}/api/ws/table/{tid}?token={t2}")
        await recv_state(ws1)
        await recv_state(ws2)
        print("join1:", (await c1.post(f"{BASE}/api/tables/{tid}/join", json={"buy_in": table["buy_in_min"]})).text)
        print("join2:", (await c2.post(f"{BASE}/api/tables/{tid}/join", json={"buy_in": table["buy_in_min"]})).text)

        st = await drain(ws1)
        h = (st or {}).get("hand")
        print("hand after join:", None if not h else
              {k: h[k] for k in ("street", "pot", "to_act", "ended", "hand_number")})
        if not h or h.get("ended"):
            print("RESULT: no fresh hand started -> table stuck (stale ended hand)")
            await ws1.close(); await ws2.close()
            return
        await drain(ws2, timeout=2)

        seat_owner = {p["seat"]: p["user_id"] for p in st["players"]}
        actor = seat_owner[h["to_act"]]
        ws = ws1 if actor == u1["id"] else ws2
        other = ws2 if ws is ws1 else ws1
        print(f"seat {h['to_act']} folds...")
        await ws.send(json.dumps({"type": "action", "action": "fold"}))
        try:
            after = await asyncio.wait_for(recv_state(ws, timeout=10), timeout=11)
            ah = after.get("hand") or {}
            print("state after fold:", {k: ah.get(k) for k in
                                        ("street", "pot", "ended", "winners", "hand_number")})
            print("RESULT: hand-end broadcast OK")
        except asyncio.TimeoutError:
            print("RESULT: NO broadcast after fold within 10s -> server hung "
                  "(nested asyncio.Lock deadlock in _post_action_flow)")

        # is the socket still alive at all?
        try:
            await ws.send(json.dumps({"type": "ping"}))
            raw = await asyncio.wait_for(ws.recv(), timeout=8)
            print("ping response:", raw[:120])
        except Exception as e:
            print("socket unresponsive after fold:", repr(e))

        # wait for next hand
        await asyncio.sleep(8)
        st2 = await drain(other, timeout=3)
        h2 = (st2 or {}).get("hand") or {}
        print("next hand:", {k: h2.get(k) for k in ("street", "pot", "ended", "hand_number")})

        hist = await c1.get(f"{BASE}/api/hands/mine")
        print("hand history count:", len(hist.json()))

        await ws1.close(); await ws2.close()
        await c1.post(f"{BASE}/api/tables/{tid}/leave")
        await c2.post(f"{BASE}/api/tables/{tid}/leave")


asyncio.run(main())

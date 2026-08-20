"""Diagnostic: log the state timeline across 3 hands to find where the flow stalls."""
import json
import sys
import time

import requests
from websockets.sync.client import connect

sys.path.insert(0, "/app/backend/tests")
from conftest import BASE_URL, register_user  # noqa

WS = BASE_URL.replace("https://", "wss://")


def main():
    tables = requests.get(f"{BASE_URL}/api/tables", timeout=30).json()
    empty = sorted([t for t in tables if t["seated"] == 0], key=lambda t: t["big_blind"])
    if not empty:
        print("NO EMPTY TABLE", [(t["name"], t["seated"]) for t in tables])
        return
    table = empty[0]
    tid = table["id"]
    print("table:", table["name"], table["stakes"])
    buy_in = max(table["buy_in_min"], min(table["buy_in_max"], table["big_blind"] * 60))
    sessions = []
    for i in range(2):
        s, _, _ = register_user(prefix=f"DIAG{i}_")
        r = s.post(f"{BASE_URL}/api/tables/{tid}/join", json={"buy_in": buy_in}, timeout=30)
        print("join", r.status_code, r.text[:120])
        sessions.append(s)

    conns = []
    for s in sessions:
        uid = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["id"]
        tok = s.post(f"{BASE_URL}/api/auth/ws-token", timeout=30).json()["token"]
        ws = connect(f"{WS}/api/ws/table/{tid}?token={tok}", open_timeout=20)
        conns.append({"uid": uid, "ws": ws, "state": None, "session": s})

    def pump(c, t=0.4):
        end = time.time() + t
        while time.time() < end:
            try:
                m = json.loads(c["ws"].recv(timeout=max(0.05, end - time.time())))
            except Exception:
                break
            if m.get("type") == "state":
                c["state"] = m["state"]
            elif m.get("type") == "error":
                print("  WS ERROR:", m)

    t0 = time.time()
    last_sig = None
    end = time.time() + 170
    while time.time() < end:
        for c in conns:
            pump(c, 0.4)
        st = conns[0]["state"] or {}
        h = st.get("hand")
        sig = (h and (h["hand_number"], h["street"], h["to_act"], h["ended"]),
               bool(st.get("next_hand_at")))
        if sig != last_sig:
            print(f"[{time.time()-t0:6.1f}] hand={sig[0]} next_hand_at={sig[1]} "
                  f"stacks={[(p['seat'], p['stack']) for p in st.get('players', [])]}")
            last_sig = sig
        if not h:
            time.sleep(0.4)
            continue
        if h["ended"] or h["to_act"] is None:
            time.sleep(0.5)
            continue
        owner = next((p["user_id"] for p in st["players"] if p["seat"] == h["to_act"]), None)
        c = next((c for c in conns if c["uid"] == owner), None)
        if not c:
            time.sleep(0.4)
            continue
        pump(c, 0.3)
        legal = (c["state"] or {}).get("legal_actions") or {}
        if not legal:
            time.sleep(0.4)
            continue
        a = "check" if legal.get("can_check") else "call"
        c["ws"].send(json.dumps({"type": "action", "action": a, "amount": 0}))
        time.sleep(0.7)

    for c in conns:
        c["ws"].close()
    for c in conns:
        r = c["session"].post(f"{BASE_URL}/api/tables/{tid}/leave", timeout=40)
        print("leave", r.status_code, r.text[:120])


main()

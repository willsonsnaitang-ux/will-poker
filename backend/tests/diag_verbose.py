"""Verbose diagnostic: play hands and log every loop iteration + server-side view."""
import json
import os
import time
import uuid

import requests
import websocket

BASE = os.environ.get("BASE_URL", "https://poker-play-ca.preview.emergentagent.com")
TABLE_NAME = "Rideau Rapids"


def register():
    email = f"dg_{uuid.uuid4().hex[:8]}@qa-willpoker.com"
    requests.post(f"{BASE}/api/auth/register", json={
        "email": email, "password": "Test@1234", "username": "dg" + uuid.uuid4().hex[:6]}, timeout=30).raise_for_status()
    s = requests.Session()
    s.post(f"{BASE}/api/auth/login", json={"email": email, "password": "Test@1234"}, timeout=30).raise_for_status()
    me = s.get(f"{BASE}/api/auth/me", timeout=30).json()
    tok = s.post(f"{BASE}/api/auth/ws-token", timeout=30).json()["token"]
    return s, me, tok


class C:
    def __init__(self, table_id, tok, uid, tag):
        self.ws = websocket.create_connection(
            BASE.replace("https://", "wss://") + f"/api/ws/table/{table_id}?token={tok}", timeout=20)
        self.uid, self.tag, self.state, self.msgs = uid, tag, None, 0

    def pump(self, t=0.4):
        self.ws.settimeout(t)
        while True:
            try:
                m = json.loads(self.ws.recv())
            except Exception:
                return
            self.msgs += 1
            if m.get("type") == "state":
                self.state = m["state"]
            elif m.get("type") == "error":
                print(f"   !! {self.tag} server error: {m}")

    def act(self, action, amount=0):
        print(f"   -> {self.tag} sends {action} {amount}")
        self.ws.send(json.dumps({"type": "action", "action": action, "amount": amount}))


tbl = next(t for t in requests.get(f"{BASE}/api/tables", timeout=30).json() if t["name"] == TABLE_NAME)
print("table", tbl["name"], "seated", tbl["seated"])
sa, ua, ta = register()
sb, ub, tb = register()
for s in (sa, sb):
    print("join", s.post(f"{BASE}/api/tables/{tbl['id']}/join", json={"buy_in": tbl["buy_in_min"]}, timeout=30).text[:80])
ca = C(tbl["id"], ta, ua["id"], "A")
cb = C(tbl["id"], tb, ub["id"], "B")
clients = {ua["id"]: ca, ub["id"]: cb}
t0 = time.time()
done, seen, last = [], [], None
while time.time() - t0 < 120 and len(done) < 4:
    ca.pump(0.3)
    cb.pump(0.3)
    st = ca.state or {}
    h = st.get("hand")
    sig = None if not h else (h["hand_number"], h["street"], h["to_act"], h["ended"])
    if sig != last:
        print(f"[{time.time()-t0:6.1f}] A-view {sig} nextHand={st.get('next_hand_at') is not None} msgsA={ca.msgs} msgsB={cb.msgs}")
        last = sig
    if not h:
        time.sleep(0.4)
        continue
    if h["ended"]:
        if h["hand_id"] not in done:
            done.append(h["hand_id"])
            print(f"[{time.time()-t0:6.1f}] HAND {h['hand_number']} ended winners={[(w.get('username'), w['amount']) for w in h['winners']]}")
        time.sleep(0.5)
        continue
    ta_seat = h.get("to_act")
    if ta_seat is None:
        time.sleep(0.3)
        continue
    owner = next((p["user_id"] for p in st["players"] if p["seat"] == ta_seat), None)
    c = clients.get(owner)
    if not c:
        print("   ?? unknown owner for seat", ta_seat)
        time.sleep(0.3)
        continue
    c.pump(0.3)
    legal = (c.state or {}).get("legal_actions") or {}
    if not legal:
        srv = requests.get(f"{BASE}/api/tables", timeout=15).json()
        srvt = next(x for x in srv if x["id"] == tbl["id"])
        print(f"   .. {c.tag} has no legal actions (seat {ta_seat}); server in_hand={srvt['in_hand']} seated={srvt['seated']}; its own view={((c.state or {}).get('hand') or {}).get('hand_number')}/{((c.state or {}).get('hand') or {}).get('to_act')}")
        time.sleep(1.0)
        continue
    c.act("check" if legal.get("can_check") else "call")
    time.sleep(0.6)

print("completed", len(done))
for s in (sa, sb):
    t = time.time()
    r = s.post(f"{BASE}/api/tables/{tbl['id']}/leave", timeout=15)
    print("leave", r.status_code, r.text[:90], f"{time.time()-t:.1f}s")

"""Standalone diagnostic: 4 consecutive heads-up hands on a dedicated table."""
import json
import os
import sys
import time
import uuid

import requests
import websocket

BASE = os.environ.get("BASE_URL", "https://poker-play-ca.preview.emergentagent.com")
TABLE_NAME = sys.argv[1] if len(sys.argv) > 1 else "Niagara Nightly"


def register():
    email = f"diag_{uuid.uuid4().hex[:8]}@qa-willpoker.com"
    r = requests.post(f"{BASE}/api/auth/register", json={
        "email": email, "password": "Test@1234", "username": "diag" + uuid.uuid4().hex[:6]}, timeout=30)
    r.raise_for_status()
    user = r.json()
    s = requests.Session()
    lr = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": "Test@1234"}, timeout=30)
    lr.raise_for_status()
    tok = s.post(f"{BASE}/api/auth/ws-token", timeout=30).json()["token"]
    return s, user, tok


class C:
    def __init__(self, table_id, tok, uid):
        url = BASE.replace("https://", "wss://") + f"/api/ws/table/{table_id}?token={tok}"
        self.ws = websocket.create_connection(url, timeout=20)
        self.uid = uid
        self.state = None

    def pump(self, t=0.4):
        self.ws.settimeout(t)
        while True:
            try:
                m = json.loads(self.ws.recv())
            except Exception:
                return
            if m.get("type") == "state":
                self.state = m["state"]

    def act(self, action, amount=0):
        self.ws.send(json.dumps({"type": "action", "action": action, "amount": amount}))


tables = requests.get(f"{BASE}/api/tables", timeout=30).json()
tbl = next(t for t in tables if t["name"] == TABLE_NAME)
print("table", tbl["name"], "seated", tbl["seated"])
sa, ua, ta = register()
sb, ub, tb = register()
buy = tbl["buy_in_min"]
for s in (sa, sb):
    r = s.post(f"{BASE}/api/tables/{tbl['id']}/join", json={"buy_in": buy}, timeout=30)
    print("join", r.status_code, r.text[:120])

ca, cb = C(tbl["id"], ta, ua["id"]), C(tbl["id"], tb, ub["id"])
clients = {ua["id"]: ca, ub["id"]: cb}
seen, done, dealers = [], [], []
t0 = time.time()
while time.time() - t0 < 150 and len(done) < 4:
    for c in (ca, cb):
        c.pump(0.3)
    st = ca.state or {}
    hand = st.get("hand")
    if not hand:
        time.sleep(0.5)
        continue
    hid = hand["hand_id"]
    if hid not in seen:
        seen.append(hid)
        dealers.append(hand["dealer_seat"])
        print(f"[{time.time()-t0:6.1f}] HAND {len(seen)} started dealer={hand['dealer_seat']} sb={hand['sb_seat']} bb={hand['bb_seat']} blinds={[a for a in hand['action_log'] if a['action']=='blind']}")
        assert hand["sb_seat"] != hand["bb_seat"], "SB and BB are the same seat!"
    if hand["ended"]:
        if hid not in done:
            done.append(hid)
            print(f"[{time.time()-t0:6.1f}] hand ended winners={[(w.get('username'), w['amount'], w.get('hand')) for w in hand['winners']]} next_hand_at={st.get('next_hand_at') is not None}")
        time.sleep(0.6)
        continue
    to_act = hand.get("to_act")
    if to_act is None:
        time.sleep(0.3)
        continue
    owner = next((p["user_id"] for p in st["players"] if p["seat"] == to_act), None)
    c = clients.get(owner)
    if not c:
        time.sleep(0.3)
        continue
    c.pump(0.3)
    legal = (c.state or {}).get("legal_actions") or {}
    if not legal:
        time.sleep(0.3)
        continue
    c.act("check" if legal.get("can_check") else "call")
    time.sleep(0.5)

print("hands completed:", len(done), "dealers:", dealers)
# post-hand responsiveness
cb.ws.send(json.dumps({"type": "chat", "text": "still alive"}))
time.sleep(1)
ca.pump(1.0)
print("chat seen:", [m["text"] for m in (ca.state or {}).get("chat", [])][-2:])
for s in (sa, sb):
    t = time.time()
    r = s.post(f"{BASE}/api/tables/{tbl['id']}/leave", timeout=15)
    print("leave", r.status_code, r.text[:120], f"{time.time()-t:.1f}s")
print("RESULT", "PASS" if len(done) >= 4 else "FAIL")

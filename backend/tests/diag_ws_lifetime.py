"""Diagnostic: how long does a table WebSocket stay open? Print close code/reason."""
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
    tid = tables[0]["id"]
    s, _, _ = register_user(prefix="WSLIFE_")
    tok = s.post(f"{BASE_URL}/api/auth/ws-token", timeout=30).json()["token"]
    ws = connect(f"{WS}/api/ws/table/{tid}?token={tok}", open_timeout=20)
    t0 = time.time()
    try:
        while time.time() - t0 < 200:
            try:
                msg = json.loads(ws.recv(timeout=5))
                print(f"[{time.time()-t0:6.1f}] recv {msg.get('type')}", flush=True)
            except TimeoutError:
                pass
            ws.send(json.dumps({"type": "ping"}))
            time.sleep(5)
    except Exception as e:
        print(f"[{time.time()-t0:6.1f}] CLOSED: {type(e).__name__}: {e}")
        print("close code:", getattr(ws, 'close_code', None),
              "reason:", getattr(ws, 'close_reason', None))
        return
    print(f"survived {time.time()-t0:.0f}s")


main()

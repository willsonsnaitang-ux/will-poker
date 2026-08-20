"""Verify a graceful backend restart returns seated stacks to bankroll."""
import subprocess
import sys
import time

import requests

sys.path.insert(0, "/app/backend/tests")
from conftest import BASE_URL, register_user  # noqa


def main():
    tables = requests.get(f"{BASE_URL}/api/tables", timeout=30).json()
    empty = sorted([t for t in tables if t["seated"] == 0], key=lambda t: t["big_blind"])
    if not empty:
        print("FAIL: no empty table", [(t["name"], t["seated"]) for t in tables])
        return
    t = empty[0]
    s, _, _ = register_user(prefix="RESTART_")
    before = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["bankroll"]
    buy_in = t["buy_in_min"]
    r = s.post(f"{BASE_URL}/api/tables/{t['id']}/join", json={"buy_in": buy_in}, timeout=30)
    print("join", r.status_code)
    after_join = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["bankroll"]
    print(f"bankroll before={before} after_join={after_join} (buy_in={buy_in})")
    assert after_join == before - buy_in, "buy-in not debited correctly"

    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True)
    for _ in range(30):
        time.sleep(2)
        try:
            if requests.get(f"{BASE_URL}/api/health", timeout=10).status_code == 200:
                break
        except Exception:
            pass
    time.sleep(2)
    after_restart = s.get(f"{BASE_URL}/api/auth/me", timeout=30).json()["bankroll"]
    print(f"bankroll after_restart={after_restart}")
    if after_restart == before:
        print("PASS: stack returned to bankroll on restart")
    else:
        print(f"FAIL: chips lost/duplicated: expected {before}, got {after_restart}")
    tables2 = requests.get(f"{BASE_URL}/api/tables", timeout=30).json()
    print("seated after restart:", [(x["name"], x["seated"]) for x in tables2])


main()

"""Utility: log in QA users and force-leave every table so browser tests start clean."""
import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
TABLES = [
    "932e2f57-b853-4c4f-9683-13774ea9c386",
    "fab6ec67-2ab7-4cb9-a8b2-86e97d9139d2",
    "7e7780a2-5594-4cf0-98ad-3c401b828e57",
    "b8ff7795-1148-40e5-832a-a125b4caadeb",
]
USERS = [
    ("qa_a1786528450@qa-willpoker.com", "Test@1234"),
    ("qa_b1786528450@qa-willpoker.com", "Test@1234"),
    ("qa1@qa-willpoker.com", "Test@1234"),
]

for email, pwd in USERS:
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    print(email, "login", r.status_code)
    if r.status_code != 200:
        continue
    tok = r.json().get("access_token") or r.json().get("token")
    h = {"Authorization": f"Bearer {tok}"} if tok else {}
    for t in TABLES:
        rr = s.post(f"{BASE}/api/tables/{t}/leave", headers=h, timeout=30)
        print("  leave", t[:8], rr.status_code)

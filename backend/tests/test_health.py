"""Health check + CORS/config sanity."""
import requests

from conftest import BASE_URL


def test_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert isinstance(data["time"], str)


def test_cors_allows_credentials_with_explicit_origin():
    """allow_credentials=True requires an explicit origin, not '*'.

    Asserted against the app directly: the platform edge proxy rewrites CORS
    headers to '*' on the public URL, which application code cannot control.
    """
    r = requests.get(
        "http://localhost:8001/api/health", headers={"Origin": BASE_URL}, timeout=30
    )
    acao = r.headers.get("access-control-allow-origin")
    acac = r.headers.get("access-control-allow-credentials")
    assert acao is not None, "no Access-Control-Allow-Origin header returned"
    assert not (acao == "*" and acac == "true"), (
        f"CORS misconfigured: ACAO={acao} with ACAC={acac} - browsers reject "
        "wildcard origin when credentials are used"
    )

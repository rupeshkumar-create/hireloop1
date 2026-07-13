from fastapi.testclient import TestClient

from hireloop_api.main import app

client = TestClient(app)


def test_list_markets_public_india_only() -> None:
    resp = client.get("/api/v1/markets")
    assert resp.status_code == 200
    data = resp.json()
    assert "markets" in data
    codes = {m["code"] for m in data["markets"]}
    assert codes == {"IN"}
    assert data["default_market"] == "IN"
    assert data["supported_codes"] == ["IN"]
    assert "IN" in data["enabled_codes"]

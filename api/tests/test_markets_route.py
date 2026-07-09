from fastapi.testclient import TestClient

from hireloop_api.main import app

client = TestClient(app)


def test_list_markets_public() -> None:
    resp = client.get("/api/v1/markets")
    assert resp.status_code == 200
    data = resp.json()
    assert "markets" in data
    codes = {m["code"] for m in data["markets"]}
    assert "IN" in codes
    assert "US" in codes
    assert "DE" in codes
    assert "SG" in codes
    assert len(codes) >= 12
    assert data["default_market"] == "IN"

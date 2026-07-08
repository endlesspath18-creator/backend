import pytest

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["status"] == "OK"
    assert "Marketplace Server is running" in json_data["message"]

def test_not_found(client):
    response = client.get("/invalid-route-name-xyz")
    assert response.status_code == 404
    json_data = response.json()
    assert json_data["success"] is False
    assert json_data["error"] == "NOT_FOUND"

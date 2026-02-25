from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "Teiken Claw AI Agent System"

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

if __name__ == "__main__":
    print("Running basic tests...")
    test_root()
    test_health()
    print("All tests passed!")
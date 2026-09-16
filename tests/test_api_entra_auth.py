from fastapi.testclient import TestClient

from camera_bridge.api import app


def test_entra_principal_can_list_cameras(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "app-service-instance")
    client = TestClient(app)

    response = client.get(
        "/api/cameras",
        headers={
            "X-MS-CLIENT-PRINCIPAL-ID": "entra-object-id",
            "X-MS-CLIENT-PRINCIPAL-NAME": "user@example.com",
        },
    )

    assert response.status_code == 200


def test_camera_listing_rejects_missing_credentials(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "app-service-instance")
    client = TestClient(app)

    response = client.get("/api/cameras")

    assert response.status_code == 401


def test_entra_headers_are_not_trusted_outside_app_service(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("WEBSITE_INSTANCE_ID", raising=False)
    client = TestClient(app)

    response = client.get(
        "/api/cameras",
        headers={"X-MS-CLIENT-PRINCIPAL-ID": "spoofed-object-id"},
    )

    assert response.status_code == 401
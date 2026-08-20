from fastapi.testclient import TestClient


def test_config_exposes_default_source_upload_cap(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_SOURCE_UPLOAD_MAX_BYTES", raising=False)

    from api.main import app

    response = TestClient(app).get("/api/config")

    assert response.status_code == 200
    assert response.json()["sourceUploadMaxBytes"] == 500 * 1024 * 1024


def test_config_exposes_overridden_source_upload_cap(monkeypatch):
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_SOURCE_UPLOAD_MAX_BYTES", str(750 * 1024 * 1024)
    )

    from api.main import app

    response = TestClient(app).get("/api/config")

    assert response.status_code == 200
    assert response.json()["sourceUploadMaxBytes"] == 750 * 1024 * 1024

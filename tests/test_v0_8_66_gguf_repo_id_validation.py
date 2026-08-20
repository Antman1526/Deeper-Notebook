"""v0.8.66 (audit S-1) — POST /api/local-models/download must validate `repo_id`
to the HuggingFace `namespace/name` shape before it is interpolated into the
download URL. `filename` was already guarded; `repo_id` was not.
"""

from __future__ import annotations

import types

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    async def _fake_start_download(repo_id, filename, dest_dir):
        return types.SimpleNamespace(
            job_id="job:1",
            status="downloading",
            target_path=str(dest_dir / filename),
            bytes_downloaded=0,
            bytes_total=None,
        )

    import deeper_notebook.local_models as lm

    monkeypatch.setattr(lm, "start_download", _fake_start_download, raising=False)

    from api.main import app

    return TestClient(app)


@pytest.mark.parametrize(
    "bad_repo_id",
    [
        "../../etc/passwd",
        "a/b/c",  # too many segments
        "no-slash",  # missing namespace
        "x@evil.com/y",  # @ in path
        "ns/name?x=1",  # query smuggle
        "ns/name#frag",  # fragment
        "ns /name",  # whitespace
        "/leadingslash",
        "ns/..",  # traversal segment
    ],
)
def test_download_rejects_bad_repo_id(client, bad_repo_id):
    r = client.post(
        "/api/local-models/download",
        json={"repo_id": bad_repo_id, "filename": "model.gguf"},
    )
    assert r.status_code == 400, (bad_repo_id, r.text)
    assert "repo_id" in r.json()["detail"]


def test_download_accepts_valid_repo_id(client):
    r = client.post(
        "/api/local-models/download",
        json={
            "repo_id": "bartowski/Qwen2.5-7B-Instruct-GGUF",
            "filename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["job_id"] == "job:1"

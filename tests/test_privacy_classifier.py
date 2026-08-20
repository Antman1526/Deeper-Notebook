"""v0.8.57 — Phase 5.2b-1: model-backed PII layer for the privacy gate.

An optional local OpenAI-compatible classifier catches unstructured PII the
regex floor can't. Additive + best-effort: unconfigured / errors → [] (regex
floor still applies). These tests mock httpx — no live endpoint.
"""

from __future__ import annotations

import pytest

from deeper_notebook.ai import privacy_classifier as pc
from deeper_notebook.ai.privacy_gate import apply_privacy_gate
from deeper_notebook.ai.router import ModelChoice

# ---------------------------------------------------------------------------
# parse_categories
# ---------------------------------------------------------------------------


def test_parse_clean_array():
    assert pc.parse_categories('["person_name", "home_address"]') == [
        "home_address",
        "person_name",
    ]


def test_parse_prose_wrapped():
    out = pc.parse_categories('Sure! Here you go: ["phone_number"] — done.')
    assert out == ["phone_number"]


def test_parse_code_fenced():
    out = pc.parse_categories('```json\n["health_info"]\n```')
    assert out == ["health_info"]


def test_parse_normalizes_and_dedupes():
    out = pc.parse_categories('["Person Name", "person_name", "PERSON NAME"]')
    assert out == ["person_name"]


def test_parse_empty_and_invalid():
    assert pc.parse_categories("[]") == []
    assert pc.parse_categories("no json here") == []
    assert pc.parse_categories("") == []
    assert pc.parse_categories('{"not": "a list"}') == []
    assert pc.parse_categories("[1, 2, 3]") == []  # non-str items dropped


# ---------------------------------------------------------------------------
# classify_via_model_async
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload=None, raise_exc=None):
        self._payload = payload
        self._raise = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        if self._raise:
            raise self._raise
        return _FakeResp(self._payload)


def _patch_httpx(monkeypatch, payload=None, raise_exc=None):
    import httpx

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: _FakeAsyncClient(payload=payload, raise_exc=raise_exc),
    )


@pytest.mark.asyncio
async def test_classify_unconfigured_returns_empty(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL", raising=False)
    assert await pc.classify_via_model_async("my name is Jane Doe") == []


@pytest.mark.asyncio
async def test_classify_empty_text_returns_empty(monkeypatch):
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL", "http://localhost:9999/v1"
    )
    assert await pc.classify_via_model_async("   ") == []


@pytest.mark.asyncio
async def test_classify_parses_model_categories(monkeypatch):
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL", "http://localhost:9999/v1"
    )
    _patch_httpx(
        monkeypatch,
        payload={
            "choices": [{"message": {"content": '["person_name", "home_address"]'}}]
        },
    )
    out = await pc.classify_via_model_async("Jane Doe lives at 5 Elm St")
    assert out == ["home_address", "person_name"]


@pytest.mark.asyncio
async def test_classify_best_effort_on_error(monkeypatch):
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL", "http://localhost:9999/v1"
    )
    _patch_httpx(monkeypatch, raise_exc=RuntimeError("connection refused"))
    # Must swallow and return [] — never block chat on a flaky classifier.
    assert await pc.classify_via_model_async("anything") == []


@pytest.mark.asyncio
async def test_classify_no_choices_returns_empty(monkeypatch):
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL", "http://localhost:9999/v1"
    )
    _patch_httpx(monkeypatch, payload={"choices": []})
    assert await pc.classify_via_model_async("text") == []


def test_classifier_url_explicit_passthrough(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL", "http://host:1234/v1")
    assert pc._classifier_url() == "http://host:1234/v1"


def test_classifier_url_unset_is_none(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL", raising=False)
    assert pc._classifier_url() is None


@pytest.mark.parametrize(
    "sentinel", ["auto", "sidecar", "chat-sidecar", "local", "AUTO"]
)
def test_classifier_url_auto_resolves_to_sidecar(monkeypatch, sentinel):
    monkeypatch.setenv("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL", sentinel)
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", "http://127.0.0.1:8080/v1"
    )
    assert pc._classifier_url() == "http://127.0.0.1:8080/v1"


def test_classifier_url_auto_without_sidecar_is_none(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_URL", "auto")
    monkeypatch.delenv("DEEPER_NOTEBOOK_LOCAL_CHAT_BASE_URL", raising=False)
    assert pc._classifier_url() is None


def test_classifier_timeout_parsing(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_TIMEOUT_SEC", raising=False)
    assert pc._classifier_timeout() == 5.0
    monkeypatch.setenv("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_TIMEOUT_SEC", "2.5")
    assert pc._classifier_timeout() == 2.5
    monkeypatch.setenv("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_TIMEOUT_SEC", "0")
    assert pc._classifier_timeout() == 5.0
    monkeypatch.setenv("DEEPER_NOTEBOOK_PRIVACY_CLASSIFIER_TIMEOUT_SEC", "x")
    assert pc._classifier_timeout() == 5.0


# ---------------------------------------------------------------------------
# gate integration — extra_findings union
# ---------------------------------------------------------------------------

CLOUD = ModelChoice("model:cloud", "cloud: oversized")


def test_gate_reroutes_on_model_finding_when_regex_clean(monkeypatch):
    """Content with NO structured secrets (regex clean) but the model flags
    unstructured PII → the gate still reroutes cloud→local."""
    out = apply_privacy_gate(
        CLOUD,
        content="Jane mentioned she lives near the park.",  # no regex hit
        local_model_id="model:local",
        cloud_model_id="model:cloud",
        mode="on",
        extra_findings=["person_name", "home_address"],
    )
    assert out.model_id == "model:local"
    assert "privacy-gate" in out.reason
    assert "person_name" in out.reason


def test_gate_passthrough_when_no_findings_at_all(monkeypatch):
    out = apply_privacy_gate(
        CLOUD,
        content="what's the capital of France?",
        local_model_id="model:local",
        cloud_model_id="model:cloud",
        mode="on",
        extra_findings=[],
    )
    assert out is CLOUD


def test_gate_unions_regex_and_model_findings(monkeypatch):
    """Both a regex secret AND a model finding present → both named in reason."""
    out = apply_privacy_gate(
        CLOUD,
        content="email me at a@b.com",  # regex: email
        local_model_id="model:local",
        cloud_model_id="model:cloud",
        mode="on",
        extra_findings=["person_name"],
    )
    assert out.model_id == "model:local"
    assert "email" in out.reason and "person_name" in out.reason


# ---------------------------------------------------------------------------
# v0.8.58 — findings_out (surfaced to the response)
# ---------------------------------------------------------------------------


def test_findings_out_populated_when_gate_acts():
    out_list: list[str] = []
    apply_privacy_gate(
        CLOUD,
        content="ssn 123-45-6789",
        local_model_id="model:local",
        cloud_model_id="model:cloud",
        mode="on",
        findings_out=out_list,
    )
    assert "us_ssn" in out_list


def test_findings_out_includes_model_categories():
    out_list: list[str] = []
    apply_privacy_gate(
        CLOUD,
        content="clean of regex",
        local_model_id="model:local",
        cloud_model_id="model:cloud",
        mode="on",
        extra_findings=["person_name"],
        findings_out=out_list,
    )
    assert out_list == ["person_name"]


def test_findings_out_empty_on_passthrough():
    out_list: list[str] = []
    apply_privacy_gate(
        CLOUD,
        content="what is the capital of France?",
        local_model_id="model:local",
        cloud_model_id="model:cloud",
        mode="on",
        findings_out=out_list,
    )
    assert out_list == []  # nothing detected → not populated


def test_findings_out_populated_before_block(monkeypatch):
    """Even on the no-local BLOCK path, findings_out is populated (before the
    ConfigurationError) so the caller could log the categories."""
    from deeper_notebook.exceptions import ConfigurationError

    out_list: list[str] = []
    with pytest.raises(ConfigurationError):
        apply_privacy_gate(
            CLOUD,
            content="ssn 123-45-6789",
            local_model_id=None,
            cloud_model_id="model:cloud",
            mode="on",
            findings_out=out_list,
        )
    assert "us_ssn" in out_list

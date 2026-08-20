"""v0.8.51 — Phase 5.2a: fail-closed privacy gate.

Keeps a cloud-bound turn on-device (or blocks it) when it contains
structured secrets/PII. Pure detector + pure gate decision — no live
services. Default-off behaviour is also pinned (zero change unless opted in).
"""

from __future__ import annotations

import pytest

from deeper_notebook.ai import privacy_gate as pg
from deeper_notebook.ai.router import ModelChoice
from deeper_notebook.exceptions import ConfigurationError

# ---------------------------------------------------------------------------
# detect_sensitive
# ---------------------------------------------------------------------------


def test_detect_clean_text_is_empty():
    assert pg.detect_sensitive("the quick brown fox jumps over 42 lazy dogs") == []
    assert pg.detect_sensitive("") == []
    assert pg.detect_sensitive(None) == []  # type: ignore[arg-type]


def test_detect_email():
    assert "email" in pg.detect_sensitive("reach me at jane.doe@example.com please")


def test_detect_us_ssn():
    assert "us_ssn" in pg.detect_sensitive("my ssn is 123-45-6789")


def test_detect_aws_access_key():
    assert "aws_access_key" in pg.detect_sensitive("AKIAIOSFODNN7EXAMPLE is the key")


def test_detect_github_token():
    tok = "ghp_" + "a" * 36
    assert "github_token" in pg.detect_sensitive(f"token={tok}")


def test_detect_openai_key():
    assert "openai_key" in pg.detect_sensitive("OPENAI key sk-abcdefghij0123456789XYZ")
    proj = "sk-proj-" + "A1b2" * 8
    assert "openai_key" in pg.detect_sensitive(f"key {proj}")


def test_detect_google_api_key():
    key = "AIza" + "B" * 35
    assert "google_api_key" in pg.detect_sensitive(f"GOOGLE_API_KEY={key}")


def test_detect_slack_token():
    assert "slack_token" in pg.detect_sensitive("xoxb-123456789012-abcdefghijkl")


def test_detect_private_key_block():
    assert "private_key_block" in pg.detect_sensitive(
        "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
    )


def test_detect_secret_assignment():
    assert "secret_assignment" in pg.detect_sensitive('password = "hunter2xyz"')
    assert "secret_assignment" in pg.detect_sensitive("api_key: 9f8e7d6c5b4a")


def test_detect_credit_card_luhn_valid():
    # 4242 4242 4242 4242 is a well-known Luhn-valid test card.
    assert "credit_card" in pg.detect_sensitive("card 4242 4242 4242 4242 exp 12/29")


def test_detect_credit_card_rejects_luhn_invalid():
    # 16 digits that fail Luhn → NOT flagged as a card (avoids false positives
    # on order numbers / IDs).
    findings = pg.detect_sensitive("order number 1234 5678 9012 3456 shipped")
    assert "credit_card" not in findings


def test_luhn_helper():
    assert pg._luhn_ok("4242424242424242") is True
    assert pg._luhn_ok("4242424242424241") is False
    assert pg._luhn_ok("123") is False  # too short


def test_detect_multiple_categories_sorted_unique():
    text = "email a@b.co and ssn 123-45-6789 and a@b.co again"
    out = pg.detect_sensitive(text)
    assert out == sorted(out)
    assert out.count("email") == 1  # de-duplicated


# ---------------------------------------------------------------------------
# _privacy_gate_enabled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("on", ["on", "1", "true", "yes", "local", "LOCAL-ONLY"])
def test_gate_enabled_truthy(monkeypatch, on):
    monkeypatch.setenv("DEEPER_NOTEBOOK_PRIVACY_GATE", on)
    assert pg._privacy_gate_enabled() is True


@pytest.mark.parametrize("off", ["", "off", "0", "false", "no", "nonsense"])
def test_gate_disabled(monkeypatch, off):
    monkeypatch.setenv("DEEPER_NOTEBOOK_PRIVACY_GATE", off)
    assert pg._privacy_gate_enabled() is False


def test_gate_default_off(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_PRIVACY_GATE", raising=False)
    assert pg._privacy_gate_enabled() is False


# ---------------------------------------------------------------------------
# apply_privacy_gate
# ---------------------------------------------------------------------------

CLOUD = ModelChoice("model:cloud", "cloud: oversized")
LOCAL = ModelChoice("model:local", "local: healthy")


def test_gate_off_is_passthrough():
    out = pg.apply_privacy_gate(
        CLOUD,
        content="ssn 123-45-6789",
        local_model_id="model:local",
        cloud_model_id="model:cloud",
        mode="off",
    )
    assert out is CLOUD  # untouched


def test_gate_on_clean_content_passthrough():
    out = pg.apply_privacy_gate(
        CLOUD,
        content="just a normal question",
        local_model_id="model:local",
        cloud_model_id="model:cloud",
        mode="on",
    )
    assert out is CLOUD


def test_gate_on_local_choice_passthrough():
    """Already going local → nothing to gate, even with secrets present."""
    out = pg.apply_privacy_gate(
        LOCAL,
        content="ssn 123-45-6789",
        local_model_id="model:local",
        cloud_model_id="model:cloud",
        mode="on",
    )
    assert out is LOCAL


def test_gate_on_cloud_sensitive_reroutes_to_local(monkeypatch):
    out = pg.apply_privacy_gate(
        CLOUD,
        content="my ssn is 123-45-6789",
        local_model_id="model:local",
        cloud_model_id="model:cloud",
        mode="on",
    )
    assert out.model_id == "model:local"
    assert "privacy-gate" in out.reason
    assert "us_ssn" in out.reason


def test_gate_on_cloud_sensitive_no_local_blocks():
    with pytest.raises(ConfigurationError) as ei:
        pg.apply_privacy_gate(
            CLOUD,
            content="key sk-abcdefghij0123456789XYZ",
            local_model_id=None,
            cloud_model_id="model:cloud",
            mode="on",
        )
    assert "Privacy gate blocked" in str(ei.value)
    assert "openai_key" in str(ei.value)


def test_gate_reads_env_when_mode_none(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_PRIVACY_GATE", "on")
    out = pg.apply_privacy_gate(
        CLOUD,
        content="ssn 123-45-6789",
        local_model_id="model:local",
        cloud_model_id="model:cloud",  # mode=None → read env
    )
    assert out.model_id == "model:local"

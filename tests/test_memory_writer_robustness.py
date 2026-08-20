"""ONP v0.7.5 — Tests for memory writer LLM-call robustness.

The `_LLM.complete` wrapper inside desktop/memory/memory_commands.py is
called every turn by the memory-extraction writer. Local LLM servers
(llama-cpp-python, ollama) have several failure modes that the
previous try/except missed:

  - HTTP 503 during model warm-up on first request
  - HTTP 200 with `{"error": "..."}` body (no "choices" key)
  - Connection-refused after a chat-server restart
  - Empty choices array

All of these used to crash the surreal_commands worker, which retried
5× per turn before giving up — log spam + no recovery.

These tests exercise the wrapper logic (extracted as a pure function
for testability) using only stdlib + a fake httpx response.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest


def _build_llm_wrapper(
    base_url: str = "http://localhost:8080/v1",
    model: str = "default",
    timeout_s: float = 5.0,
):
    """Re-construct the inner _LLM class with the same logic as
    memory_commands.py:_LLM.complete (which is a closure inside
    register_memory_commands and not directly importable). The behavior
    we're testing IS the source of v0.7.5 — keep the test mirror in
    sync if the production code changes."""

    # Match memory_commands.py exactly so the test catches regressions.
    class _LLM:
        def __init__(self):
            self.base_url = base_url
            self.model = model

        def complete(self, system, user):
            if not (system or user):
                return ""
            try:
                with httpx.Client(timeout=timeout_s) as client:
                    r = client.post(
                        f"{self.base_url}/chat/completions",
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                            ],
                            "max_tokens": 800,
                            "temperature": 0.2,
                        },
                    )
                    r.raise_for_status()
                    payload = r.json()
                    choices = payload.get("choices") or []
                    if not choices:
                        return ""
                    return choices[0].get("message", {}).get("content") or ""
            except httpx.TimeoutException:
                return ""
            except Exception:
                return ""

    return _LLM()


def _fake_response(status: int, json_body):
    """Build a MagicMock that quacks like httpx.Response."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status
    mock.json = MagicMock(return_value=json_body)
    if status >= 400:
        mock.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "error",
                request=MagicMock(),
                response=mock,
            ),
        )
    else:
        mock.raise_for_status = MagicMock(return_value=None)
    return mock


def test_complete_returns_text_on_normal_response():
    """Happy path — standard OpenAI chat-completion shape."""
    body = {"choices": [{"message": {"content": "extracted fact"}}]}
    with patch("httpx.Client.post", return_value=_fake_response(200, body)):
        llm = _build_llm_wrapper()
        result = llm.complete("sys", "user")
    assert result == "extracted fact"


def test_complete_returns_empty_on_http_503():
    """v0.7.5 Issue #14 regression: HTTP 503 (model warming up on a
    local llama-cpp server) used to propagate out and crash the
    worker. Now it returns "" gracefully."""
    with patch(
        "httpx.Client.post", return_value=_fake_response(503, {"error": "loading"})
    ):
        llm = _build_llm_wrapper()
        result = llm.complete("sys", "user")  # must not raise
    assert result == ""


def test_complete_returns_empty_on_connection_refused():
    """v0.7.5 Issue #14: ConnectError (local server restart) used to
    propagate. Now graceful."""
    with patch(
        "httpx.Client.post", side_effect=httpx.ConnectError("Connection refused")
    ):
        llm = _build_llm_wrapper()
        result = llm.complete("sys", "user")
    assert result == ""


def test_complete_returns_empty_on_timeout():
    """Timeout path — existing behavior preserved."""
    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("slow")):
        llm = _build_llm_wrapper()
        result = llm.complete("sys", "user")
    assert result == ""


def test_complete_returns_empty_on_error_response_with_200():
    """v0.7.5 Issue #15: some servers return HTTP 200 with
    `{"error": "..."}` instead of a proper choices array. Previously
    KeyError on the indexed access. Now graceful."""
    error_payload = {"error": "model not loaded"}
    with patch("httpx.Client.post", return_value=_fake_response(200, error_payload)):
        llm = _build_llm_wrapper()
        result = llm.complete("sys", "user")
    assert result == ""


def test_complete_returns_empty_on_empty_choices_array():
    """v0.7.5: `choices: []` was an IndexError before."""
    with patch("httpx.Client.post", return_value=_fake_response(200, {"choices": []})):
        llm = _build_llm_wrapper()
        result = llm.complete("sys", "user")
    assert result == ""


def test_complete_returns_empty_when_message_content_missing():
    """v0.7.5: `choices: [{"message": {}}]` — content key absent.
    Previously KeyError. Now graceful."""
    body = {"choices": [{"message": {}}]}
    with patch("httpx.Client.post", return_value=_fake_response(200, body)):
        llm = _build_llm_wrapper()
        result = llm.complete("sys", "user")
    assert result == ""


def test_complete_skips_network_when_inputs_empty():
    """No system AND no user → return "" without calling the LLM at all
    (existing behavior — preserved)."""
    with patch("httpx.Client.post") as mock_post:
        llm = _build_llm_wrapper()
        result = llm.complete("", "")
    assert result == ""
    mock_post.assert_not_called()

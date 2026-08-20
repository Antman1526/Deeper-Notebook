"""v0.8.67h — DEEPER_NOTEBOOK_CHAT_LLM_GGUF pins a specific chat model over the heuristic.

Addresses "the loaded chat model doesn't match what I selected": the launcher
picks the chat GGUF via pick_chat_llm_file's scorer, independent of the UI's
model choice. DEEPER_NOTEBOOK_CHAT_LLM_GGUF lets the user force a specific file; if unset or
absent, the scorer still runs so the sidecar always spawns.
"""

from __future__ import annotations

from desktop.auto_register.assigner import pick_chat_llm_file


def _mk(d, names):
    for n in names:
        (d / n).write_bytes(b"\0" * (2 * 1024 * 1024))  # >1MB so it isn't skipped


def test_pin_forces_named_model(tmp_path, monkeypatch):
    _mk(tmp_path, ["Hermes-3-Llama-3.1-8B-Q4_K_M.gguf", "Qwen3.5-9B-Q4_K_M.gguf"])
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_LLM_GGUF", "Qwen3.5-9B-Q4_K_M.gguf")
    assert pick_chat_llm_file(tmp_path).name == "Qwen3.5-9B-Q4_K_M.gguf"


def test_pin_without_extension_and_case_insensitive(tmp_path, monkeypatch):
    _mk(tmp_path, ["Qwen3.5-9B-Q4_K_M.gguf", "Hermes-3-Llama-3.1-8B-Q4_K_M.gguf"])
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_CHAT_LLM_GGUF", "qwen3.5-9b-q4_k_m"
    )  # no .gguf, lowercase
    assert pick_chat_llm_file(tmp_path).name == "Qwen3.5-9B-Q4_K_M.gguf"


def test_pin_not_found_falls_through_to_heuristic(tmp_path, monkeypatch):
    _mk(tmp_path, ["Hermes-3-Llama-3.1-8B-Q4_K_M.gguf"])
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_LLM_GGUF", "DoesNotExist.gguf")
    r = pick_chat_llm_file(tmp_path)
    assert r is not None and r.name == "Hermes-3-Llama-3.1-8B-Q4_K_M.gguf"


def test_no_pin_uses_heuristic(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_LLM_GGUF", raising=False)
    _mk(tmp_path, ["Hermes-3-Llama-3.1-8B-Q4_K_M.gguf"])
    r = pick_chat_llm_file(tmp_path)
    assert r is not None and r.name.endswith(".gguf")

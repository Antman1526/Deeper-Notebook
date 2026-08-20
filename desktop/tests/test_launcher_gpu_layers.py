"""v0.8.67c — `_n_gpu_layers` resolves llama.cpp GPU offload for the sidecars.

Regression for the silent-chatbot bug: the chat/embed sidecars were spawned with
no `--n_gpu_layers`, so llama-cpp-python defaulted to 0 and ran the whole model
on CPU — on Apple Silicon that's so slow the chat never returns a completion.
These tests pin the contract: macOS offloads all layers by default (-1), other
OSes stay on CPU (0) unless the operator opts in, and a bad env value can never
silently disable offload on macOS.
"""

from __future__ import annotations

import pytest

from desktop.launcher import _n_gpu_layers


def test_macos_default_offloads_all_layers(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_LLM_N_GPU_LAYERS", raising=False)
    monkeypatch.setattr("desktop.launcher.sys.platform", "darwin")
    assert _n_gpu_layers("DEEPER_NOTEBOOK_CHAT_LLM_N_GPU_LAYERS") == "-1"


def test_non_macos_defaults_to_cpu(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_LLM_N_GPU_LAYERS", raising=False)
    monkeypatch.setattr("desktop.launcher.sys.platform", "linux")
    assert _n_gpu_layers("DEEPER_NOTEBOOK_CHAT_LLM_N_GPU_LAYERS") == "0"


def test_env_override_is_honored(monkeypatch):
    monkeypatch.setattr("desktop.launcher.sys.platform", "darwin")
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_LLM_N_GPU_LAYERS", "20")
    assert _n_gpu_layers("DEEPER_NOTEBOOK_CHAT_LLM_N_GPU_LAYERS") == "20"


def test_env_override_can_force_cpu_on_mac(monkeypatch):
    monkeypatch.setattr("desktop.launcher.sys.platform", "darwin")
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_LLM_N_GPU_LAYERS", "0")
    assert _n_gpu_layers("DEEPER_NOTEBOOK_CHAT_LLM_N_GPU_LAYERS") == "0"


@pytest.mark.parametrize("bad", ["all", "", "  ", "abc", "1.5"])
def test_unparseable_env_falls_back_to_mac_default(monkeypatch, bad):
    # A garbage override must NOT silently disable offload on macOS.
    monkeypatch.setattr("desktop.launcher.sys.platform", "darwin")
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_LLM_N_GPU_LAYERS", bad)
    assert _n_gpu_layers("DEEPER_NOTEBOOK_CHAT_LLM_N_GPU_LAYERS") == "-1"


def test_custom_mac_default(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_EMBED_N_GPU_LAYERS", raising=False)
    monkeypatch.setattr("desktop.launcher.sys.platform", "darwin")
    assert _n_gpu_layers("DEEPER_NOTEBOOK_EMBED_N_GPU_LAYERS", mac_default=0) == "0"

"""v0.8.67i — `Supervisor._default_ctx_max` scales the chat-LLM context
ceiling to available unified memory on Apple Silicon.

Regression for context_length_exceeded: pre-v0.8.67i the cap was hardcoded
to 32768, so a large all-sources chat context (e.g. ~72K tokens for a
26-source notebook) failed even on a 64 GB Mac whose model (Hermes-3,
131072 native) could comfortably hold it. The user then saw only a generic
chat failure. These tests pin:

  - the RAM tiers (>=56 GiB -> 98304, >=40 -> 65536, >=28 -> 49152, else 32768),
  - the non-darwin floor (32768) — the KV-cache RAM math is Apple-Silicon
    unified-memory specific,
  - the sysconf-unavailable / sysconf-raises fallbacks (never crash boot),
  - that an explicit ONP_CHAT_LLM_CTX_MAX still overrides the adaptive
    default (operator retains full control).
"""
from __future__ import annotations

import pytest

from desktop.launcher import Supervisor


def _patch_ram(monkeypatch, gib, platform="darwin"):
    """Make desktop.launcher see `gib` GiB of physical RAM on `platform`."""
    monkeypatch.setattr("desktop.launcher.sys.platform", platform)
    page = 16384
    pages = int(gib * (1024 ** 3) / page)
    monkeypatch.setattr(
        "desktop.launcher.os.sysconf_names",
        {"SC_PHYS_PAGES": 1, "SC_PAGE_SIZE": 2},
    )

    def fake_sysconf(name):
        if name == "SC_PHYS_PAGES":
            return pages
        if name == "SC_PAGE_SIZE":
            return page
        raise ValueError(name)

    monkeypatch.setattr("desktop.launcher.os.sysconf", fake_sysconf)


@pytest.mark.parametrize(
    "gib,expected",
    [
        (128, 98304),
        (64, 98304),   # the user's machine
        (56, 98304),   # lower edge of the top tier
        (48, 65536),
        (40, 65536),   # lower edge
        (32, 49152),
        (28, 49152),   # lower edge
        (24, 32768),
        (16, 32768),
        (8, 32768),
    ],
)
def test_ram_tiers(monkeypatch, gib, expected):
    _patch_ram(monkeypatch, gib)
    assert Supervisor._default_ctx_max() == expected


def test_non_darwin_uses_floor(monkeypatch):
    # The KV-cache sizing assumes Apple-Silicon unified memory; on other
    # platforms stay at the historical conservative default.
    _patch_ram(monkeypatch, 128, platform="linux")
    assert Supervisor._default_ctx_max() == 32768


def test_sysconf_names_missing_falls_back(monkeypatch):
    monkeypatch.setattr("desktop.launcher.sys.platform", "darwin")
    monkeypatch.setattr("desktop.launcher.os.sysconf_names", {})
    assert Supervisor._default_ctx_max() == 32768


def test_sysconf_raises_falls_back(monkeypatch):
    monkeypatch.setattr("desktop.launcher.sys.platform", "darwin")
    monkeypatch.setattr(
        "desktop.launcher.os.sysconf_names",
        {"SC_PHYS_PAGES": 1, "SC_PAGE_SIZE": 2},
    )

    def boom(_name):
        raise OSError("sysconf unavailable")

    monkeypatch.setattr("desktop.launcher.os.sysconf", boom)
    assert Supervisor._default_ctx_max() == 32768


def test_explicit_ctx_max_overrides_adaptive_default(monkeypatch):
    """An explicit ONP_CHAT_LLM_CTX_MAX wins over the RAM-aware default so
    operators keep full control (e.g. capping a low-RAM machine)."""
    sup = Supervisor.__new__(Supervisor)  # no __init__ side effects needed
    sup.chat_llm_path = None  # forces the "return ctx_max" branch
    _patch_ram(monkeypatch, 64)  # adaptive would be 98304
    monkeypatch.setenv("ONP_CHAT_LLM_CTX_MAX", "8192")
    monkeypatch.delenv("ONP_CHAT_LLM_CTX", raising=False)
    assert sup._resolve_chat_llm_n_ctx() == 8192


def test_no_env_uses_adaptive_default(monkeypatch):
    """With no env overrides and no chat GGUF, _resolve falls back to the
    adaptive ctx_max (not the old hardcoded 32768) on a 64 GB Mac."""
    sup = Supervisor.__new__(Supervisor)
    sup.chat_llm_path = None
    _patch_ram(monkeypatch, 64)
    monkeypatch.delenv("ONP_CHAT_LLM_CTX_MAX", raising=False)
    monkeypatch.delenv("ONP_CHAT_LLM_CTX", raising=False)
    assert sup._resolve_chat_llm_n_ctx() == 98304

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
  - that an explicit DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX still overrides the adaptive
    default (operator retains full control).
"""

from __future__ import annotations

import pytest

from desktop.launcher import Supervisor


def _patch_ram(monkeypatch, gib, platform="darwin"):
    """Make desktop.launcher see `gib` GiB of physical RAM on `platform`."""
    monkeypatch.setattr("desktop.launcher.sys.platform", platform)
    page = 16384
    pages = int(gib * (1024**3) / page)
    monkeypatch.setattr(
        "desktop.launcher.os.sysconf_names",
        {"SC_PHYS_PAGES": 1, "SC_PAGE_SIZE": 2},
        raising=False,
    )

    def fake_sysconf(name):
        if name == "SC_PHYS_PAGES":
            return pages
        if name == "SC_PAGE_SIZE":
            return page
        raise ValueError(name)

    monkeypatch.setattr("desktop.launcher.os.sysconf", fake_sysconf, raising=False)
    # v0.8.67l — report ample AVAILABLE RAM so the pressure backoff is a no-op
    # here; the backoff itself is covered by the _pressure_adjusted_ctx_max
    # tests below. Keeps the total-RAM-tier assertions deterministic.
    monkeypatch.setattr(
        "desktop.launcher.Supervisor._available_ram_bytes",
        staticmethod(lambda: gib * (1024**3)),
    )


@pytest.mark.parametrize(
    "gib,expected",
    [
        (128, 98304),
        (64, 98304),  # the user's machine
        (56, 98304),  # lower edge of the top tier
        (48, 65536),
        (40, 65536),  # lower edge
        (32, 49152),
        (28, 49152),  # lower edge
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


def test_windows_without_sysconf_names_uses_floor(monkeypatch):
    # Windows does not define os.sysconf_names. The shared test helper must
    # still be able to simulate its RAM without assuming POSIX APIs exist.
    monkeypatch.delattr("desktop.launcher.os.sysconf_names", raising=False)
    _patch_ram(monkeypatch, 128, platform="win32")
    assert Supervisor._default_ctx_max() == 32768


def test_sysconf_names_missing_falls_back(monkeypatch):
    monkeypatch.setattr("desktop.launcher.sys.platform", "darwin")
    monkeypatch.delattr("desktop.launcher.os.sysconf_names", raising=False)
    assert Supervisor._default_ctx_max() == 32768


def test_sysconf_raises_falls_back(monkeypatch):
    monkeypatch.setattr("desktop.launcher.sys.platform", "darwin")
    monkeypatch.setattr(
        "desktop.launcher.os.sysconf_names",
        {"SC_PHYS_PAGES": 1, "SC_PAGE_SIZE": 2},
        raising=False,
    )

    def boom(_name):
        raise OSError("sysconf unavailable")

    monkeypatch.setattr("desktop.launcher.os.sysconf", boom, raising=False)
    assert Supervisor._default_ctx_max() == 32768


def test_explicit_ctx_max_overrides_adaptive_default(monkeypatch):
    """An explicit DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX wins over the RAM-aware default so
    operators keep full control (e.g. capping a low-RAM machine)."""
    sup = Supervisor.__new__(Supervisor)  # no __init__ side effects needed
    sup.chat_llm_path = None  # forces the "return ctx_max" branch
    _patch_ram(monkeypatch, 64)  # adaptive would be 98304
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX", "8192")
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX", raising=False)
    assert sup._resolve_chat_llm_n_ctx() == 8192


def test_no_env_uses_adaptive_default(monkeypatch):
    """With no env overrides and no chat GGUF, _resolve falls back to the
    adaptive ctx_max (not the old hardcoded 32768) on a 64 GB Mac."""
    sup = Supervisor.__new__(Supervisor)
    sup.chat_llm_path = None
    _patch_ram(monkeypatch, 64)  # also mocks _available_ram_bytes (ample)
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_CHAT_LLM_CTX", raising=False)
    assert sup._resolve_chat_llm_n_ctx() == 98304


# --- v0.8.67l memory-pressure backoff (pure) ----------------------------------

_GIB = 1024**3


def test_pressure_backoff_noop_when_roomy():
    # 64 GiB available easily holds the 98304 tier (~12 GiB KV + 5 GiB headroom).
    assert Supervisor._pressure_adjusted_ctx_max(98304, 64 * _GIB) == 98304


def test_pressure_backoff_steps_down_when_tight():
    # ~15 GiB available: 98304 needs ~17 GiB → step down to 65536 (~13 GiB fits).
    assert Supervisor._pressure_adjusted_ctx_max(98304, 15 * _GIB) == 65536


def test_pressure_backoff_floor_when_starved():
    assert Supervisor._pressure_adjusted_ctx_max(98304, 1 * _GIB) == 32768


def test_pressure_backoff_noop_when_unknown():
    assert Supervisor._pressure_adjusted_ctx_max(98304, None) == 98304
    assert Supervisor._pressure_adjusted_ctx_max(65536, 0) == 65536


def test_pressure_backoff_never_exceeds_tier():
    # A small tier stays small even with huge available RAM.
    assert Supervisor._pressure_adjusted_ctx_max(32768, 256 * _GIB) == 32768

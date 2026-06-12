"""
Pytest configuration file.

This file ensures that the project root is in the Python path,
allowing tests to import from the api and open_notebook modules.
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure password auth is disabled for tests BEFORE any imports
# The PasswordAuthMiddleware skips auth when this env var is not set
# Set to empty string instead of deleting to prevent it from being reloaded
os.environ["OPEN_NOTEBOOK_PASSWORD"] = ""

# Load environment variables from .env file
# This must be done BEFORE any imports that depend on environment variables
from dotenv import load_dotenv

# Load .env file from project root
dotenv_path = Path(__file__).parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    print(f"Loaded environment variables from {dotenv_path}")
else:
    print(f"Warning: .env file not found at {dotenv_path}")

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# v0.8.64 — `.env` may now carry real web-search provider keys
# (SERPER_API_KEY / TAVILY_API_KEY / SEARXNG_BASE_URL), which conftest loads via
# load_dotenv above. Left in place, those would silently enable the built-in
# `web_search` tool inside the chat tool loop — which (a) changes tool-loop
# tests that assume no tools are bound (e.g. v0.8.56's "no outcome when no tools
# bound") and (b) risks real network calls from the suite. Strip them before
# EVERY test so the suite is deterministic regardless of the developer's .env;
# tests that exercise web search opt in by setting the vars explicitly (see
# tests/test_v0_8_64_web_search.py). monkeypatch auto-restores after each test.
_WEB_SEARCH_ENV_VARS = (
    "SERPER_API_KEY",
    "TAVILY_API_KEY",
    "SEARXNG_BASE_URL",
    "ONP_WEB_SEARCH_PROVIDER",
    "ONP_WEB_SEARCH_MAX_RESULTS",
    "ONP_WEB_SEARCH_TIMEOUT_SEC",
)


@pytest.fixture(autouse=True)
def _isolate_web_search_env(monkeypatch):
    for name in _WEB_SEARCH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield


# v0.8.68 — pin the network-state service to "online" for every test so the
# suite is deterministic regardless of the machine's actual connectivity
# (the offline gate / web_search short-circuit would otherwise change
# behavior on an airgapped CI box, and the real TCP probe is a network
# call the suite must never make). Tests that exercise offline behavior
# opt in by monkeypatching get_network_state_with_settings / _probe_once
# themselves (see tests/test_offline_gate.py, tests/test_web_search_offline.py).
@pytest.fixture(autouse=True)
def _pin_network_state_online(monkeypatch):
    from open_notebook.health import network

    network.reset_network_state_for_tests()
    monkeypatch.setattr(network, "_probe_once", lambda: True)
    yield
    network.reset_network_state_for_tests()

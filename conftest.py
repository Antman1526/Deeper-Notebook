"""Root pytest conftest — process-environment isolation for every test path.

Lives at the repository root, not under tests/, because `testpaths` is
["desktop/tests", "tests"] and tests/integration/ is a third collection root.
A conftest under tests/ would leave the other two unprotected, and env leakage
does not respect directory boundaries: the combined suite runs desktop/tests
FIRST, so anything it leaks lands in tests/ afterwards.
"""

import os

import pytest

# v0.8.102 — restore os.environ around EVERY test.
#
# `monkeypatch.setenv("DEEPER_NOTEBOOK_X", ...)` undoes only the key it wrote.
# But `normalize_product_environment` deliberately MIRRORS a canonical name into
# each of its legacy spellings (the alias prefixes are enumerated in
# `deeper_notebook/environment.py`'s SETTINGS table — deliberately not repeated
# here, so this comment cannot drift from them and so it stays clear of the
# identity audit's active-identity scan). monkeypatch has no record of writes it
# did not make, so those mirrors outlive the test. That is the footgun recorded
# as §4.7 in docs/recreation/PROJECT-DEEP-DIVE.md, and it is not theoretical:
# instrumenting a full run found four tests leaking real state into everything
# that ran after them —
#
#   test_evidence_studio_artifact_api.py   (evidence-studio feature flag)
#   test_v0_8_40b_hot_swap.py              (active GGUF model)
#   test_v0_8_40d_env_refresh.py (x2)      (local n_ctx)
#
# Leaked feature flags are how a suite with no random ordering still produces
# different results on consecutive runs: tests/test_environment_aliases.py
# builds a subprocess env from `dict(os.environ)`, so it inherits whatever ran
# before it. Four consecutive full runs failed four different sets of tests.
#
# Fixing those four individually would require every future test to know every
# mirror spelling — the same caller-discipline assumption the SurrealQL
# identifier guards exist to reject. Restoring the whole mapping fixes the class
# instead, and costs one dict copy per test.
#
# WHY A HOOKWRAPPER AND NOT AN autouse FIXTURE: an autouse fixture tears down
# while other fixtures are still finalizing, so it observes monkeypatch's own
# not-yet-undone writes and reports them as leaks — measured, 67 false positives
# across three files. Wrapping the whole runtest protocol observes the
# environment only after every fixture has finalized, which is precisely the
# state the NEXT test inherits.
#
# Set DEEPER_NOTEBOOK_TEST_STRICT_ENV=1 to have leaks printed as they happen
# (they are still repaired). That is how the four above were isolated from the
# noise, and how the next one gets found.


# OPT-OUT: tests that deliberately own process env at SESSION scope.
#
# tests/integration/conftest.py mints a throwaway SurrealDB namespace once per
# session and exports SURREAL_NAMESPACE/SURREAL_DATABASE for every test in the
# directory to share. Session-fixture setup runs inside the FIRST test's
# protocol, so this hook would see those exports as that test's mutations and
# restore them away — starving every subsequent test, which then fails in the
# driver with "params.0: Input should be a valid string". Found exactly that way.
#
# Skipping marked items is the honest trade: those suites are gated behind
# SURREAL_INTEGRATION, run as their own CI job, and manage env on purpose.
_ENV_RESTORE_OPT_OUT_MARKERS = ("integration_surreal",)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    if any(item.get_closest_marker(name) for name in _ENV_RESTORE_OPT_OUT_MARKERS):
        yield
        return
    before = dict(os.environ)
    yield
    after = dict(os.environ)
    if after == before:
        return
    if os.environ.get("DEEPER_NOTEBOOK_TEST_STRICT_ENV") == "1":
        added = sorted(after.keys() - before.keys())
        removed = sorted(before.keys() - after.keys())
        changed = sorted(
            k for k in (before.keys() & after.keys()) if before[k] != after[k]
        )
        # Printed, not raised: this hook runs after the test's own report is
        # finalized, so raising here surfaces as a confusing protocol-level
        # error rather than a failure attributed to the offending test.
        print(f"\nENV LEAK {item.nodeid}: added={added} removed={removed} changed={changed}")
    os.environ.clear()
    os.environ.update(before)

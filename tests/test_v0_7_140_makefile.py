"""v0.7.140 Makefile hygiene tests.

Two real bugs caught the user when they ran `make start-all` for
the first time:

  1. Three targets (`dev`, `full`, `start-all`) referenced
     `docker-compose.dev.yml` or `docker-compose.full.yml` —
     neither file exists in the repo. Only `docker-compose.yml`
     ships.

  2. `start-all` invoked the API as `uv run run_api.py &` —
     missing the `--env-file .env` flag the worker line above it
     correctly uses. Symptom: API came up without seeing
     DEEPER_NOTEBOOK_ENCRYPTION_KEY etc.

These are regression-tests for both: a future commit that
reintroduces either bug fails the Makefile-shape check before
landing.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_MAKEFILE = Path("Makefile")
_COMPOSE_FILES_PRESENT = {p.name for p in Path(".").glob("docker-compose*.yml")}


def _makefile_text() -> str:
    return _MAKEFILE.read_text()


def test_every_compose_file_referenced_actually_exists():
    """Every `-f docker-compose*.yml` flag in the Makefile must
    name a file that's actually checked in. Catches the v0.7.140
    bug where three targets named the dev/full variants that don't
    exist."""
    src = _makefile_text()
    referenced = set(re.findall(r"-f\s+(docker-compose[\w.]*\.yml)", src))
    missing = referenced - _COMPOSE_FILES_PRESENT
    assert not missing, (
        f"Makefile references compose files that don't exist: {missing}. "
        f"Either add the file or update the target to use one of: "
        f"{_COMPOSE_FILES_PRESENT}."
    )


def test_start_all_passes_env_file_to_api():
    """`start-all` runs three uv processes (API, worker, frontend).
    The API and worker BOTH need `--env-file .env` to see secrets.
    The worker line had it from the start; the API line was missing
    it until v0.7.140 — fixing one without the other lets the bug
    creep back in via a future edit that mirrors the (then-wrong)
    API line."""
    src = _makefile_text()
    # Walk the start-all block: from `start-all:` to the next
    # blank line at column 0 (or end of file).
    start = src.find("start-all:")
    assert start >= 0, "start-all target missing from Makefile"
    # End of block: next line that begins with a non-tab, non-#
    # character (i.e., the next target or a fully-flush comment).
    block = src[start:]
    end_match = re.search(r"\n[^\t#\n]", block[len("start-all:"):])
    if end_match:
        block = block[: len("start-all:") + end_match.start()]

    # Find every `uv run` invocation inside the block. Each one
    # that calls run_api.py OR surreal-commands-worker MUST be
    # preceded by --env-file .env.
    api_calls = re.findall(r"uv run[^&\n]*run_api\.py", block)
    assert api_calls, "Expected at least one `uv run run_api.py` in start-all"
    for call in api_calls:
        assert "--env-file" in call, (
            f"start-all invokes API without --env-file: {call!r}. The API "
            "needs to see DEEPER_NOTEBOOK_ENCRYPTION_KEY etc. The worker "
            "line gets this right; the API line should match."
        )

    worker_calls = re.findall(r"uv run[^&\n]*surreal-commands-worker", block)
    assert worker_calls, (
        "Expected at least one `uv run surreal-commands-worker` in start-all"
    )
    for call in worker_calls:
        assert "--env-file" in call, (
            f"start-all invokes worker without --env-file: {call!r}"
        )


def test_makefile_parses_clean():
    """The Makefile must `make -n` parse without error — a stricter
    check than just reading text. Catches mistakes like dangling
    backslash continuations or unterminated quotes that the regex
    tests above can't see."""
    if shutil.which("make") is None:
        pytest.skip("make not available on this runner")
    # Use --question / -q? No — that returns non-zero when a target
    # is out of date. -n (dry-run) just expands rules without
    # running them and surfaces parse errors via exit code 2.
    proc = subprocess.run(
        ["make", "-n", "status"],   # 'status' is the cheapest target
        capture_output=True,
        text=True,
        cwd=str(_MAKEFILE.parent),
    )
    # exit 0 (success) or exit 1 (target wanted recompile, but
    # syntax was fine) are both OK. exit 2 is "Makefile parse
    # error" — fail loudly.
    assert proc.returncode != 2, (
        f"Makefile has a parse error:\n{proc.stderr}"
    )


def test_dev_and_full_targets_use_existing_compose_file():
    """`make dev` and `make full` previously failed because they
    named docker-compose.dev.yml / docker-compose.full.yml which
    don't exist. Pin this so a future re-introduction of the
    naming has to also add the file."""
    src = _makefile_text()
    # Pull out the dev: + full: target bodies (one line each).
    dev_match = re.search(r"^dev:\s*\n(.*?)(?=^\S|^\s*$|\Z)", src, re.MULTILINE | re.DOTALL)
    full_match = re.search(r"^full:\s*\n(.*?)(?=^\S|^\s*$|\Z)", src, re.MULTILINE | re.DOTALL)
    assert dev_match, "dev: target missing"
    assert full_match, "full: target missing"
    for label, body in (("dev", dev_match.group(1)), ("full", full_match.group(1))):
        compose_refs = re.findall(r"docker-compose[\w.]*\.yml", body)
        for ref in compose_refs:
            assert ref in _COMPOSE_FILES_PRESENT, (
                f"`make {label}` references {ref} but only "
                f"{_COMPOSE_FILES_PRESENT} are checked in"
            )

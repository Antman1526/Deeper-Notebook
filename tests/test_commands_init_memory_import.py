"""v0.7.47 — regression test for memory_commands runtime registration.

Before v0.7.47, `commands/__init__.py` imported four sibling modules
(embedding_commands, example_commands, podcast_commands,
source_commands) but NEVER imported memory_commands. The launcher
copies `desktop/memory/memory_commands.py` into the commands/ dir at
startup, but the bundled __init__.py didn't pick it up — so the
worker never registered `memory_extract_turn` and
`memory_summarize_session` commands. Every chat turn that fired
those jobs queued rows with status="new" that nobody ever picked up.

This test pins the guarded-import contract: when a `memory_commands`
module exists in the package, it gets imported and the symbols are
bound to the package namespace.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from textwrap import dedent

import pytest


def _reload_commands():
    """Drop and re-import the `commands` package and its memory submodule
    so each test starts fresh."""
    for name in list(sys.modules.keys()):
        if name == "commands" or name.startswith("commands."):
            del sys.modules[name]
    return importlib.import_module("commands")


def test_commands_imports_normally_without_memory_module(monkeypatch, tmp_path):
    """When `commands/memory_commands.py` doesn't exist (fresh install,
    no-memory build, dev environments), the package still imports —
    no ImportError leaks out."""
    # The fixture environment ships memory_commands at
    # desktop/memory/memory_commands.py but NOT at commands/. So a
    # standard import should succeed AND `memory_extract_turn` should
    # NOT be in the namespace.
    pkg = _reload_commands()
    # Core commands are always present
    assert hasattr(pkg, "embed_note_command")
    assert hasattr(pkg, "generate_podcast_command")
    # __all__ shape sane
    assert "embed_note_command" in pkg.__all__


def test_memory_commands_registered_when_module_present(tmp_path, monkeypatch):
    """When memory_commands.py is present in the package dir at import
    time, the guarded import picks it up and the symbols are bound."""
    # Find the commands package on disk
    import commands as _commands_pkg

    pkg_path = Path(_commands_pkg.__file__).parent
    target = pkg_path / "memory_commands.py"

    # If it's already there (e.g. a real install ran), test against the
    # real one. Otherwise plant a stub that mimics the real module.
    cleanup = False
    if not target.exists():
        target.write_text(
            dedent("""
            # Stub memory_commands for v0.7.47 regression test.
            def memory_extract_turn(*args, **kwargs):
                return {"ok": True, "stub": True}

            def memory_summarize_session(*args, **kwargs):
                return {"ok": True, "stub": True}
        """).strip()
            + "\n"
        )
        cleanup = True

    try:
        pkg = _reload_commands()
        # The guarded import must have bound both symbols.
        assert hasattr(pkg, "memory_extract_turn"), (
            "memory_extract_turn missing from commands namespace"
        )
        assert hasattr(pkg, "memory_summarize_session"), (
            "memory_summarize_session missing from commands namespace"
        )
        # __all__ extended to include them so `from commands import *`
        # doesn't silently drop the memory commands
        assert "memory_extract_turn" in pkg.__all__
        assert "memory_summarize_session" in pkg.__all__
    finally:
        if cleanup:
            target.unlink()
            # And purge from sys.modules so other tests see the
            # post-cleanup state
            for name in list(sys.modules.keys()):
                if name == "commands" or name.startswith("commands."):
                    del sys.modules[name]


def test_memory_commands_import_failure_doesnt_break_package(tmp_path):
    """If memory_commands.py exists but raises ImportError on its own
    imports (broken install, missing dep), the rest of the commands
    package still loads cleanly. The guard only catches ImportError
    on the FROM line; other exceptions still propagate."""
    import commands as _commands_pkg

    pkg_path = Path(_commands_pkg.__file__).parent
    target = pkg_path / "memory_commands.py"

    backup = target.read_text() if target.exists() else None
    # Plant a memory_commands that raises a sub-ImportError on its
    # internal imports. This simulates "the file exists but its
    # dependencies are missing".
    target.write_text("from nonexistent_module_for_testing import foo\n")
    try:
        pkg = _reload_commands()
        # Core commands still loaded
        assert hasattr(pkg, "embed_note_command")
        # memory symbols NOT bound
        assert not hasattr(pkg, "memory_extract_turn")
    finally:
        if backup is None:
            target.unlink()
        else:
            target.write_text(backup)
        for name in list(sys.modules.keys()):
            if name == "commands" or name.startswith("commands."):
                del sys.modules[name]

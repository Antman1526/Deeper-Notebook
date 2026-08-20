"""v0.8.99 — every registered surreal_command exposes a resolvable input schema.

`extract_source_visual` shipped with an input model that could not build its
JSON schema: `commands/source_visual_commands.py` used
`from __future__ import annotations`, so the @command decorator saw the string
"ExtractSourceVisualInput" and the generated
`extract_source_visual_command_input` model was never fully defined.

Registration still succeeded, so the queue worked and nothing looked broken.
The defect only appeared when that module was imported in isolation — any test
batch that had already imported the type resolved the name by accident. That
made it look like runner-dependent flake rather than a real bug.

This suite imports every command module explicitly, in one process, and asserts
the whole registry can build schemas. It fails on the old code and passes on
the new, and it guards every command module, not just the one that regressed.
"""

from __future__ import annotations

import importlib

# Every module that registers commands. A new command module must be added
# here — that is the point: the registry is only as trustworthy as its
# enumeration.
COMMAND_MODULES = [
    "commands.embedding_commands",
    "commands.podcast_commands",
    "commands.podcast_staged",
    "commands.prompt_optimizer_commands",
    "commands.source_commands",
    "commands.source_visual_commands",
    "commands.studio_commands",
]


def _registry():
    for name in COMMAND_MODULES:
        importlib.import_module(name)
    from surreal_commands.core.registry import CommandRegistry

    return CommandRegistry()


def test_every_command_module_imports() -> None:
    for name in COMMAND_MODULES:
        assert importlib.import_module(name) is not None


def test_every_registered_command_input_schema_resolves() -> None:
    """No command may register an input model with unresolved forward refs."""
    registry = _registry()
    commands = registry._commands  # no public enumeration API in 1.x
    assert commands, "no commands registered — the import list is wrong"

    unresolved: list[str] = []
    for key, cmd in commands.items():
        runnable = getattr(cmd, "runnable", cmd)
        try:
            runnable.get_input_schema().model_json_schema()
        except Exception as exc:  # noqa: BLE001 - report every failure at once
            unresolved.append(f"{key}: {type(exc).__name__}: {str(exc)[:120]}")

    assert unresolved == [], (
        "command input schemas must be fully defined; a module using "
        "`from __future__ import annotations` will leave the generated model's "
        "forward reference unresolved:\n  " + "\n  ".join(unresolved)
    )


# Persisted queue identities are pinned by tests/test_persisted_queue_identifiers.py,
# which derives them from an AST inventory rather than hardcoded literals. Not
# duplicated here: a second hardcoded copy adds no protection and re-introduces
# the legacy app-name literal the identity audit exists to track.

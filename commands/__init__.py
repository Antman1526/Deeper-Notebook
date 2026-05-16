"""Surreal-commands integration for Open Notebook.

v0.7.24 — configure loguru file logging for the worker process.

The desktop launcher spawns `surreal_commands.cli.worker
--import-modules commands` as a separate Python process. That worker
is where podcast / source / embed jobs actually run — most operations
that take minutes and most things that fail in interesting ways.
Without a configured file sink, all worker output went to stderr,
and the launcher pipes worker stderr to DEVNULL in non-debug mode.
Net effect since v0.7.14: every worker job failure in production was
silently discarded; the README's `tail ~/.open-notebook-plus/logs/*.log`
story worked for the API process but not the worker that does the
long-running work.

`configure_logging("worker")` at package import time means the moment
`surreal_commands` imports this package (its first action after
starting), the worker.log sink is installed alongside api.log and
launcher.log.

Wrapped in try/except so any import-time logging failure doesn't
prevent the worker from booting — defense-in-depth only.
"""

try:
    from open_notebook.logging import configure_logging
    configure_logging("worker")
except Exception:
    # Logging setup is best-effort at import time. Even if it fails,
    # the worker must still start so we don't lose job processing.
    pass

from .embedding_commands import (
    embed_insight_command,
    embed_note_command,
    embed_source_command,
    rebuild_embeddings_command,
)
from .example_commands import analyze_data_command, process_text_command
from .podcast_commands import generate_podcast_command
from .source_commands import process_source_command

__all__ = [
    # Embedding commands
    "embed_note_command",
    "embed_insight_command",
    "embed_source_command",
    "rebuild_embeddings_command",
    # Other commands
    "generate_podcast_command",
    "process_source_command",
    "process_text_command",
    "analyze_data_command",
]

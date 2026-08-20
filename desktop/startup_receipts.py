"""Small, local-only startup timing and chat-model selection receipts.

The launcher uses this store as a best-effort optimization.  A malformed,
stale, or out-of-root receipt is treated as a cache miss so it can never alter
model ownership or prevent the normal bounded chooser from running.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
RECEIPT_FILENAME = "startup_receipt.json"
MAX_STAGES = 16
MAX_STAGE_LENGTH = 64
MAX_ELAPSED_MS = 24 * 60 * 60 * 1000
MAX_RECEIPT_BYTES = 64 * 1024

_RECEIPT_KEYS = {"schema_version", "stages", "chat_model"}
_MODEL_KEYS = {"path", "size", "mtime_ns"}


def _empty_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stages": [],
        "chat_model": None,
    }


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _valid_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_payload(value: object) -> dict[str, Any] | None:
    """Validate and copy the bounded on-disk schema, failing closed."""
    if not isinstance(value, dict) or set(value) - _RECEIPT_KEYS:
        return None
    if value.get("schema_version") != SCHEMA_VERSION:
        return None

    raw_stages = value.get("stages")
    if not isinstance(raw_stages, list) or len(raw_stages) > MAX_STAGES:
        return None
    stages: list[dict[str, Any]] = []
    for raw_stage in raw_stages:
        if not isinstance(raw_stage, dict) or set(raw_stage) != {"stage", "elapsed_ms"}:
            return None
        stage = raw_stage.get("stage")
        elapsed_ms = raw_stage.get("elapsed_ms")
        if (
            not isinstance(stage, str)
            or not stage
            or len(stage) > MAX_STAGE_LENGTH
            or not _valid_non_negative_int(elapsed_ms)
            or elapsed_ms > MAX_ELAPSED_MS
        ):
            return None
        stages.append({"stage": stage, "elapsed_ms": elapsed_ms})

    raw_model = value.get("chat_model")
    chat_model: dict[str, Any] | None
    if raw_model is None:
        chat_model = None
    elif isinstance(raw_model, dict) and set(raw_model) == _MODEL_KEYS:
        path = raw_model.get("path")
        size = raw_model.get("size")
        mtime_ns = raw_model.get("mtime_ns")
        if (
            not isinstance(path, str)
            or not path
            or len(path) > 4096
            or not _valid_non_negative_int(size)
            or not _valid_non_negative_int(mtime_ns)
        ):
            return None
        chat_model = {"path": path, "size": size, "mtime_ns": mtime_ns}
    else:
        return None

    return {
        "schema_version": SCHEMA_VERSION,
        "stages": stages,
        "chat_model": chat_model,
    }


class StartupReceiptStore:
    """Persist a bounded, atomic startup receipt below one local data root."""

    def __init__(self, root: Path):
        candidate = Path(root).expanduser()
        # Accept either the active data directory or an explicit receipt path;
        # the latter keeps the store fixture-friendly without changing the
        # launcher's root-bounded semantics.
        if candidate.suffix.lower() == ".json":
            self.path = candidate
            self.root = candidate.parent
        else:
            self.root = candidate
            self.path = candidate / RECEIPT_FILENAME
        self.receipt_path = self.path

    def _read(self) -> dict[str, Any] | None:
        try:
            if (
                self.path.is_symlink()
                or not self.path.is_file()
                or self.path.stat().st_size > MAX_RECEIPT_BYTES
            ):
                return None
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return _validate_payload(parsed)

    def _write(self, payload: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.root,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as receipt_file:
                temporary_path = Path(receipt_file.name)
                json.dump(payload, receipt_file, sort_keys=True, separators=(",", ":"))
                receipt_file.write("\n")
                receipt_file.flush()
                os.fsync(receipt_file.fileno())
            try:
                os.chmod(temporary_path, 0o600)
            except OSError:
                pass
            os.replace(temporary_path, self.path)
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    def record(self, stage: str, elapsed_ms: int) -> None:
        """Append or replace one bounded startup milestone."""
        if not isinstance(stage, str) or not stage.strip():
            return
        normalized_stage = stage.strip()[:MAX_STAGE_LENGTH]
        try:
            normalized_elapsed = int(elapsed_ms)
        except (TypeError, ValueError):
            normalized_elapsed = 0
        normalized_elapsed = max(0, min(normalized_elapsed, MAX_ELAPSED_MS))

        payload = self._read() or _empty_payload()
        stages = [
            entry for entry in payload["stages"] if entry["stage"] != normalized_stage
        ]
        stages.append({"stage": normalized_stage, "elapsed_ms": normalized_elapsed})
        payload["stages"] = stages[-MAX_STAGES:]
        self._write(payload)

    def cache_chat_model(self, path: Path, *, root: Path | None = None) -> bool:
        """Store stat metadata for a model, rejecting invalid/out-of-root paths."""
        candidate = Path(path).expanduser().resolve(strict=False)
        if candidate.suffix.lower() != ".gguf" or not candidate.is_file():
            return False
        if root is not None:
            model_root = Path(root).expanduser().resolve(strict=False)
            if not _path_is_within(candidate, model_root):
                return False
        try:
            metadata = candidate.stat()
        except OSError:
            return False

        payload = self._read() or _empty_payload()
        payload["chat_model"] = {
            "path": str(candidate),
            "size": metadata.st_size,
            "mtime_ns": metadata.st_mtime_ns,
        }
        self._write(payload)
        return True

    def clear_chat_model(self) -> None:
        payload = self._read()
        if payload is None:
            return
        if payload.get("chat_model") is None:
            return
        payload["chat_model"] = None
        self._write(payload)

    def load_chat_model(self, root: Path) -> Path | None:
        """Return a still-matching GGUF strictly contained by ``root``."""
        payload = self._read()
        if payload is None or payload.get("chat_model") is None:
            return None
        cached = payload["chat_model"]
        model_root = Path(root).expanduser().resolve(strict=False)
        raw_path = Path(cached["path"]).expanduser()
        candidate = model_root / raw_path if not raw_path.is_absolute() else raw_path
        candidate = candidate.resolve(strict=False)
        if candidate.suffix.lower() != ".gguf" or not _path_is_within(
            candidate, model_root
        ):
            return None
        try:
            metadata = candidate.stat()
        except OSError:
            return None
        if (
            not candidate.is_file()
            or metadata.st_size != cached["size"]
            or metadata.st_mtime_ns != cached["mtime_ns"]
        ):
            return None
        return candidate

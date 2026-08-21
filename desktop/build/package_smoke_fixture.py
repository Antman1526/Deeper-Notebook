"""Create isolated, offline roots for the packaged desktop smoke probe."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from desktop.config import Config
from desktop.model_downloads import (
    EMBEDDING_GGUF,
    FASTER_WHISPER_STT_DIR,
    FASTER_WHISPER_STT_FILES,
    PIPER_RYAN_CONFIG,
    PIPER_RYAN_MODEL,
    PIPER_VOICE_CONFIG,
    PIPER_VOICE_MODEL,
)

OPENCHRONICLE_PLACEHOLDER_URL = "http://127.0.0.1:8742/mcp"
FIXTURE_MANIFEST_NAME = "fixture.json"

MODEL_PLACEHOLDERS = {
    Path(EMBEDDING_GGUF[1]): int(EMBEDDING_GGUF[3] * 0.8 * 1024 * 1024),
    Path(PIPER_VOICE_MODEL[1]): int(PIPER_VOICE_MODEL[3] * 0.8 * 1024 * 1024),
    Path(PIPER_VOICE_CONFIG[1]): 2048,
    Path(PIPER_RYAN_MODEL[1]): int(PIPER_RYAN_MODEL[3] * 0.8 * 1024 * 1024),
    Path(PIPER_RYAN_CONFIG[1]): 2048,
    **{
        Path(FASTER_WHISPER_STT_DIR) / filename: minimum
        for _url, filename, minimum in FASTER_WHISPER_STT_FILES
    },
}


@dataclass(frozen=True)
class SmokeFixture:
    """Paths and environment needed by one packaged smoke invocation."""

    root: Path
    home: Path
    data_dir: Path
    model_dir: Path
    readiness_file: Path
    environment: dict[str, str]


def _path_exists_without_following(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise FileExistsError(
            f"smoke fixture root cannot be inspected: {path}"
        ) from error
    return True


def _assert_inside(root: Path, candidate: Path) -> Path:
    root_resolved = root.resolve(strict=False)
    candidate_resolved = candidate.resolve(strict=False)
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError(
            f"fixture path must remain inside the smoke fixture root: {candidate}"
        ) from error
    return candidate


def _make_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _write_private_manifest(path: Path, payload: dict[str, object]) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if len(serialized.encode("utf-8")) > 16 * 1024:
        raise ValueError("smoke fixture manifest exceeds the maximum size")
    path.write_text(serialized, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def prepare_smoke_fixture(
    root: Path, *, source_visuals: bool, uv_cache_dir: Path
) -> SmokeFixture:
    """Create one fresh provider-none, offline smoke root.

    The root is checked before any fixture path is created.  Every generated
    path is then checked against that root so a changed model-download
    constant cannot cause a placeholder to be written elsewhere.
    """
    requested_root = Path(root)
    if _path_exists_without_following(requested_root):
        raise FileExistsError(f"smoke fixture root already exists: {requested_root}")
    root = requested_root.resolve(strict=False)
    if _path_exists_without_following(root):
        raise FileExistsError(f"smoke fixture root already exists: {root}")

    home = _assert_inside(root, root / "home")
    data_dir = _assert_inside(root, root / "data")
    model_dir = _assert_inside(root, home / "Desktop" / "AI_Models")
    readiness_file = _assert_inside(root, data_dir / "desktop-readiness.json")
    config_path = _assert_inside(root, data_dir / "config.toml")
    manifest_path = _assert_inside(root, root / FIXTURE_MANIFEST_NAME)
    for relative_path in MODEL_PLACEHOLDERS:
        if not isinstance(relative_path, Path):
            raise ValueError("model placeholder paths must be pathlib.Path values")
        _assert_inside(root, model_dir / relative_path)

    root.mkdir(mode=0o700)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    _make_private_directory(home)
    _make_private_directory(home / "Desktop")
    _make_private_directory(model_dir)
    _make_private_directory(data_dir)

    Config(
        model_dir=model_dir,
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password=secrets.token_urlsafe(),
        theme="gemini-forward-light",
        openchronicle_choice="skip",
        encryption_key=secrets.token_urlsafe(),
        execution_policy="strict_local",
    ).save(config_path)

    for relative_path, minimum_size in MODEL_PLACEHOLDERS.items():
        if type(minimum_size) is not int or minimum_size < 0:
            raise ValueError("model placeholder sizes must be non-negative integers")
        placeholder = _assert_inside(root, model_dir / relative_path)
        placeholder.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(placeholder.parent, 0o700)
        except OSError:
            pass
        with placeholder.open("wb") as file:
            file.truncate(minimum_size)
        try:
            os.chmod(placeholder, 0o600)
        except OSError:
            pass

    environment = {
        "HOME": str(home),
        "DEEPER_NOTEBOOK_DATA_DIR": str(data_dir),
        "UV_CACHE_DIR": str(Path(uv_cache_dir).resolve(strict=False)),
        "UV_OFFLINE": "1",
        "OPENCHRONICLE_MCP_URL": OPENCHRONICLE_PLACEHOLDER_URL,
    }
    if not source_visuals:
        environment["DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED"] = "0"

    _write_private_manifest(
        manifest_path,
        {
            "schema_version": 1,
            "paths": {
                "root": str(root),
                "home": str(home),
                "data_dir": str(data_dir),
                "model_dir": str(model_dir),
                "readiness_file": str(readiness_file),
            },
            "environment": environment,
        },
    )
    return SmokeFixture(
        root=root,
        home=home,
        data_dir=data_dir,
        model_dir=model_dir,
        readiness_file=readiness_file,
        environment=environment,
    )

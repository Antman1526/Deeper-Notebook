"""MLX provider: scan local MLX repos and spawn mlx_lm.server."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import httpx

from desktop.ports import find_free_port
from desktop.providers import ProviderEnv


def _http_ready(port: int) -> bool:
    try:
        return httpx.get(f"http://127.0.0.1:{port}/v1/models", timeout=0.5).status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        return False


def _mlx_roots(model_dir: Path) -> list[Path]:
    if model_dir.name == "MLX":
        return [model_dir]
    mlx_dir = model_dir / "MLX"
    return [mlx_dir] if mlx_dir.exists() and mlx_dir.is_dir() else []


def _is_complete_mlx_repo(path: Path) -> bool:
    if not path.is_dir() or path.name.startswith("."):
        return False
    if not (path / "config.json").is_file():
        return False
    try:
        return any(item.is_file() and item.suffix == ".safetensors" for item in path.iterdir())
    except OSError:
        return False


class MlxProvider:
    name: str = "mlx"

    def __init__(
        self,
        model_dir: Path,
        ready_probe: Callable[[int], bool] = _http_ready,
        max_wait: float = 60.0,
        python_executable: str | Path | None = None,
    ) -> None:
        self.model_dir = model_dir
        self._ready_probe = ready_probe
        self._max_wait = max_wait
        self._python_executable: str | Path = (
            sys.executable if python_executable is None else python_executable
        )
        self._proc: subprocess.Popen | None = None
        self._port: int | None = None

    def is_available(self) -> bool:
        return bool(self.list_models())

    def list_models(self) -> list[str]:
        models: list[str] = []
        for root in _mlx_roots(self.model_dir):
            try:
                candidates = list(root.iterdir())
            except OSError:
                continue
            for repo in candidates:
                if _is_complete_mlx_repo(repo):
                    models.append(repo.relative_to(self.model_dir).as_posix())
        return sorted(models)

    def start(
        self,
        model: str,
        *,
        validate: bool = True,
        wait_for_ready: bool = True,
    ) -> ProviderEnv:
        path = self._resolve_model_path(model)
        if validate and not _is_complete_mlx_repo(path):
            raise FileNotFoundError(f"Not a complete MLX model repo: {path}")
        # v0.8.84 — a nonexistent path can never load, even for a configured
        # model that skips full repo validation. Before this check, a model
        # deleted after being configured produced the worst failure mode:
        # mlx_lm.server was spawned (stderr=DEVNULL), bound nothing, and died
        # silently — the credential then pointed at a dead port and the only
        # symptom was a "Degraded" runtime card with no cause. Fail loudly at
        # the source instead; callers already handle start() raising.
        if not path.exists():
            raise FileNotFoundError(
                f"Configured MLX model no longer exists on disk: {path} — "
                "pick an existing model in Launch Preferences"
            )
        if self._proc is not None:
            self.stop()

        port = find_free_port()
        args = [
            str(self._python_executable),
            "-m",
            "mlx_lm.server",
            "--model",
            str(path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        self._proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._port = port

        # A configured local model can legitimately take minutes to load (or
        # live on an on-demand filesystem).  The desktop shell, database, and
        # knowledge browser must not be held hostage by that optional worker.
        # Callers that own an explicit user configuration may therefore defer
        # readiness and let the model become available independently.
        env = ProviderEnv(
            OPENAI_COMPATIBLE_BASE_URL=f"http://127.0.0.1:{port}/v1",
            OPENAI_COMPATIBLE_API_KEY="sk-no-key",
        )
        if not wait_for_ready:
            return env

        deadline = time.monotonic() + self._max_wait
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    "mlx_lm.server exited prematurely "
                    f"(returncode={self._proc.returncode}) while loading model {model!r}"
                )
            if self._ready_probe(port):
                return env
            time.sleep(0.5)

        self.stop()
        raise RuntimeError(
            f"mlx_lm.server on port {port} never became ready within {self._max_wait}s "
            f"(model={model!r})"
        )

    def stop(self) -> None:
        if self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        self._proc = None
        self._port = None

    def pick_default_model(self) -> str:
        try:
            models = self.list_models()
        except Exception:
            return ""
        if not models:
            return ""
        by_name = {model.lower(): model for model in models}
        for hint in ("qwen", "north-mini-code", "devstral", "deepseek", "gemma"):
            for key, original in by_name.items():
                if hint in key:
                    return original
        return models[0]

    def _resolve_model_path(self, model: str) -> Path:
        raw_path = Path(model)
        if raw_path.is_absolute():
            path = raw_path.resolve()
        else:
            path = (self.model_dir / raw_path).resolve()
            if not path.exists() and self.model_dir.name == "MLX":
                path = (self.model_dir / raw_path.name).resolve()

        root = self.model_dir.resolve()
        if path == root or path.is_relative_to(root):
            return path
        raise FileNotFoundError(f"MLX model path must be inside {self.model_dir}: {model}")

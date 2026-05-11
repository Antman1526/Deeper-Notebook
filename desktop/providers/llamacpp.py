"""llama.cpp provider: scan a directory for GGUFs, spawn llama-cpp-python server."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import httpx

from desktop.ports import find_free_port
from desktop.providers import ProviderEnv

# Files smaller than this are treated as Git LFS pointers / aborted downloads
# and skipped during model listing.
MIN_GGUF_BYTES = 1 * 1024 * 1024


def _http_ready(port: int) -> bool:
    try:
        return httpx.get(f"http://127.0.0.1:{port}/v1/models", timeout=0.5).status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        return False


class LlamaCppProvider:
    name: str = "llamacpp"

    def __init__(
        self,
        model_dir: Path,
        ready_probe: Callable[[int], bool] = _http_ready,
        max_wait: float = 60.0,
        python_executable: Path | None = None,
    ) -> None:
        self.model_dir = model_dir
        self._ready_probe = ready_probe
        self._max_wait = max_wait
        # python_executable: interpreter used to spawn llama_cpp.server.
        # Defaults to sys.executable (unfrozen/dev); pass the venv python when
        # running inside the frozen .app so llama_cpp is importable.
        self._python_executable: Path = python_executable or Path(sys.executable)
        self._proc: subprocess.Popen | None = None
        self._port: int | None = None

    def is_available(self) -> bool:
        return any(True for _ in self._iter_ggufs())

    def list_models(self) -> list[str]:
        return sorted(str(p.relative_to(self.model_dir)) for p in self._iter_ggufs())

    def start(self, model: str) -> ProviderEnv:
        path = self.model_dir / model
        if not path.exists() or path.stat().st_size < MIN_GGUF_BYTES:
            raise FileNotFoundError(f"GGUF not found or too small: {path}")
        if self._proc is not None:
            self.stop()

        port = find_free_port()
        self._proc = subprocess.Popen(
            [str(self._python_executable), "-m", "llama_cpp.server",
             "--model", str(path),
             "--host", "127.0.0.1",
             "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._port = port

        deadline = time.monotonic() + self._max_wait
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"llama_cpp.server exited prematurely "
                                   f"(returncode={self._proc.returncode})")
            if self._ready_probe(port):
                # Upstream uses esperanto's openai_compatible provider; these
                # are the env var names esperanto's OpenAICompatibleLanguageModel
                # actually reads. (`OPENAI_API_BASE` is NOT read by upstream.)
                return ProviderEnv(
                    OPENAI_COMPATIBLE_BASE_URL=f"http://127.0.0.1:{port}/v1",
                    OPENAI_COMPATIBLE_API_KEY="sk-no-key",
                )
            time.sleep(0.5)

        self.stop()
        raise RuntimeError(f"llama_cpp.server on port {port} never became ready")

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
        """Choose a sensible default GGUF from the user's model dir.

        Preference order (first match wins):
          1. Hermes-3 family (best chat-tuned model in the user's typical set)
          2. Mistral-7B-Instruct (reliable baseline)
          3. Qwen2.5-7B-Instruct
          4. llama-3.2-3b (small but capable)
          5. phi-3.5-mini
          6. Any GGUF at all (first in list_models() sorted order)
        Returns "" if no usable GGUF exists.
        """
        try:
            models = self.list_models()
        except Exception:
            return ""
        if not models:
            return ""
        by_name = {m.lower(): m for m in models}
        for hint in ("hermes-3", "mistral-7b-instruct", "qwen2.5-7b-instruct",
                     "llama-3.2-3b", "phi-3.5-mini"):
            for k, original in by_name.items():
                if hint in k:
                    return original
        # Fallback: first model in sorted list (list_models already filters <1 MB files).
        return models[0]

    def _iter_ggufs(self):
        if not self.model_dir.exists():
            return
        for p in self.model_dir.rglob("*.gguf"):
            if p.is_file() and p.stat().st_size >= MIN_GGUF_BYTES:
                yield p

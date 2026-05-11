"""Process supervisor for the desktop app.

Starts SurrealDB, FastAPI (uvicorn), the open-notebook worker, and the Next.js
frontend in dependency order. Each child gets the per-session env (DB creds,
ports, model provider). Window code (window.py) opens once frontend_url returns
HTTP 200.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from desktop.progress import ProgressBus

from desktop.config import Config
from desktop.ports import find_free_ports


def _wait_tcp(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"tcp {host}:{port} never came up within {timeout}s")


def _wait_http(url: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code < 500:
                return
        except (httpx.RequestError, httpx.TimeoutException):
            pass
        time.sleep(0.3)
    raise TimeoutError(f"http {url} never returned <500 within {timeout}s")


class Supervisor:
    def __init__(
        self,
        cfg: Config,
        repo_root: Path,
        bin_dir: Path,
        surreal_arch: str,
        node_arch: str,
        extra_env: dict[str, str] | None = None,
        debug_mode: bool = False,
        log_dir: Path | None = None,
        venv_python: Path | None = None,
        upstream_root: Path | None = None,
        whisper_model_path: Path | None = None,
        piper_voices: dict[str, Path] | None = None,
        nomic_embed_path: Path | None = None,
        progress: "ProgressBus | None" = None,
    ) -> None:
        self.cfg = cfg
        self.repo_root = repo_root
        self.bin_dir = bin_dir
        self.surreal_arch = surreal_arch
        self.node_arch = node_arch
        self.extra_env = dict(extra_env or {})
        self.debug_mode = debug_mode
        self.log_dir = log_dir or (
            Path(os.environ.get("HOME", os.environ.get("USERPROFILE", ".")))
            / ".open-notebook-plus" / "logs"
        )
        # venv_python: the Python interpreter used to spawn FastAPI/worker children.
        # When None, falls back to sys.executable (unfrozen/dev path).
        self.venv_python: Path = venv_python or Path(sys.executable)
        # upstream_root: cwd for the API + worker subprocesses. Upstream code
        # uses relative paths like 'open_notebook/database/migrations/1.surrealql'
        # so cwd MUST be the directory that contains the api/ and open_notebook/
        # source trees. In the frozen .app, upstream lives at MEIPASS/upstream/;
        # the frontend lives at MEIPASS/frontend/. They're not the same dir.
        # In unfrozen/dev mode, upstream_root defaults to repo_root (they coincide).
        self.upstream_root: Path = upstream_root or repo_root
        # whisper_model_path may be a Path to a legacy ggml .bin file (kept for
        # type compatibility) OR a Path whose str() is a faster-whisper model
        # name like "base.en".  _spawn_whisper no longer checks .exists() so
        # that model-name strings (which are not real filesystem paths) work.
        self.whisper_model_path = whisper_model_path
        self.piper_voices = piper_voices or {}
        self.nomic_embed_path = nomic_embed_path
        self.progress = progress
        self._procs: list[subprocess.Popen] = []
        self._log_files: list[IO[bytes]] = []
        self.session_env: dict[str, str] = {}
        self.frontend_url: str = ""
        self.embed_port: int = 0
        self.whisper_port: int = 0
        self.piper_port: int = 0

    def start_all(self) -> None:
        (surreal_port, api_port, frontend_port,
         embed_port, whisper_port, piper_port) = find_free_ports(6)

        api_url = f"http://127.0.0.1:{api_port}"
        self.session_env = {
            **os.environ,
            **self.extra_env,
            "SURREAL_URL": f"ws://127.0.0.1:{surreal_port}/rpc",
            "SURREAL_USER": self.cfg.surreal_user,
            "SURREAL_PASSWORD": self.cfg.surreal_password,
            "SURREAL_NAMESPACE": "open_notebook",
            "SURREAL_DATABASE": "open_notebook",
            "API_PORT": str(api_port),
            "PORT": str(frontend_port),  # Next.js convention
            # Upstream Next.js reads these (see frontend/next.config.ts and
            # frontend/src/app/config/route.ts):
            # - API_URL: where the browser makes direct API calls
            # - INTERNAL_API_URL: where the Next.js server-side proxy forwards
            # - NEXT_PUBLIC_API_URL: client-bundle fallback
            # All three point at our dynamic uvicorn port.
            "API_URL": api_url,
            "INTERNAL_API_URL": api_url,
            "NEXT_PUBLIC_API_URL": api_url,
            "NEXT_PUBLIC_API_BASE": api_url,  # legacy, kept for safety
            "OPEN_NOTEBOOK_ENCRYPTION_KEY": self.cfg.encryption_key,
        }

        self._progress("supervisor.surreal", "running")
        self._spawn_surreal(surreal_port)
        _wait_tcp("127.0.0.1", surreal_port, timeout=30)
        self._progress("supervisor.surreal", "done")

        self._progress("supervisor.api", "running")
        self._spawn_api(api_port)
        # First-launch SurrealDB schema migrations + the heavy upstream import
        # chain (langchain + langgraph + podcast_creator) take 20-60 s before
        # uvicorn finishes startup. Subsequent launches are much faster but
        # we leave the generous timeout in place — better to wait than to
        # tear down an API that was about to come up.
        _wait_http(f"http://127.0.0.1:{api_port}/health", timeout=180)
        self._progress("supervisor.api", "done")

        self._progress("supervisor.worker", "running")
        self._spawn_worker()
        # Worker has no port; just give it a beat to subscribe.
        time.sleep(0.5)
        self._progress("supervisor.worker", "done")

        self._progress("supervisor.next", "running")
        self._spawn_next(frontend_port)
        _wait_http(f"http://127.0.0.1:{frontend_port}/", timeout=120)
        self.frontend_url = f"http://127.0.0.1:{frontend_port}/"
        self._progress("supervisor.next", "done")

        # New v0.3 processes — best-effort; failures don't crash the launcher.
        self._progress("supervisor.llamacpp_embed", "running")
        try:
            self._spawn_llamacpp_embed(embed_port)
            self._progress("supervisor.llamacpp_embed", "done")
        except Exception:
            self._progress("supervisor.llamacpp_embed", "error")

        self._progress("supervisor.whisper", "running")
        try:
            self._spawn_whisper(whisper_port)
            self._progress("supervisor.whisper", "done")
        except Exception:
            self._progress("supervisor.whisper", "error")

        self._progress("supervisor.piper", "running")
        try:
            self._spawn_piper(piper_port)
            self._progress("supervisor.piper", "done")
        except Exception:
            self._progress("supervisor.piper", "error")

        # Stash ports for auto_register to use.
        self.embed_port = embed_port
        self.whisper_port = whisper_port
        self.piper_port = piper_port

    def stop_all(self) -> None:
        for p in reversed(self._procs):
            try:
                p.terminate()
            except Exception:
                pass
        deadline = time.monotonic() + 5
        for p in self._procs:
            try:
                remaining = max(0.0, deadline - time.monotonic())
                p.wait(timeout=remaining if remaining > 0 else 0.1)
            except subprocess.TimeoutExpired:
                p.kill()
            except Exception:
                pass
        for f in self._log_files:
            try:
                f.close()
            except Exception:
                pass
        self._procs.clear()
        self._log_files.clear()

    def _spawn(
        self,
        args: list[str],
        cwd: Path | None = None,
        name: str = "child",
    ) -> subprocess.Popen:
        # PIPE without a reader deadlocks long-running children once the OS
        # pipe buffer fills (Surreal, uvicorn, Next all emit plenty of output).
        # In production we discard output entirely; in debug_mode we drain
        # both streams on background threads into per-child log files so
        # startup failures are recoverable.
        if self.debug_mode:
            stdout: int = subprocess.PIPE
            stderr: int = subprocess.PIPE
        else:
            stdout = subprocess.DEVNULL
            stderr = subprocess.DEVNULL

        proc = subprocess.Popen(
            args,
            cwd=str(cwd) if cwd else None,
            env=self.session_env,
            stdout=stdout,
            stderr=stderr,
        )
        self._procs.append(proc)

        if self.debug_mode and proc.stdout is not None and proc.stderr is not None:
            self._start_drainers(proc, name)

        return proc

    def _start_drainers(self, proc: subprocess.Popen, name: str) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_dir / f"{name}.log"
        log_file = open(log_path, "ab", buffering=0)
        self._log_files.append(log_file)

        def drain(stream: IO[bytes], prefix: bytes) -> None:
            try:
                for line in iter(stream.readline, b""):
                    try:
                        log_file.write(prefix + line)
                    except Exception:
                        return
            except Exception:
                return

        for stream, prefix in ((proc.stdout, b"[out] "), (proc.stderr, b"[err] ")):
            t = threading.Thread(
                target=drain, args=(stream, prefix), name=f"drain-{name}", daemon=True
            )
            t.start()

    def _spawn_surreal(self, port: int) -> None:
        ext = ".exe" if self.surreal_arch.startswith("windows") else ""
        binary = self.bin_dir / f"surreal-{self.surreal_arch}{ext}"
        data_dir = Path(os.environ.get("HOME", os.environ.get("USERPROFILE", "."))) \
            / ".open-notebook-plus" / "surreal_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        # Use --flag=value form so passwords/usernames that happen to start
        # with '-' (a real possibility from secrets.token_urlsafe which uses
        # base64url, where `-` is a valid char) aren't reparsed by clap as
        # a separate short flag like '-4'.
        self._spawn(
            [
                str(binary), "start",
                f"--user={self.cfg.surreal_user}",
                f"--pass={self.cfg.surreal_password}",
                f"--bind=127.0.0.1:{port}",
                f"file://{data_dir}",
            ],
            name="surreal",
        )

    def _spawn_api(self, port: int) -> None:
        # Use the venv python to run uvicorn directly — it's a real Python
        # interpreter with all upstream deps installed, so -m uvicorn works
        # without any internal dispatcher tricks.
        # cwd MUST be upstream_root so relative paths in upstream code resolve
        # correctly (e.g. open_notebook/database/migrations/*.surrealql).
        args = [
            str(self.venv_python), "-m", "uvicorn", "api.main:app",
            "--host", "127.0.0.1", "--port", str(port),
        ]
        self._spawn(args, cwd=self.upstream_root, name="api")

    def _spawn_worker(self) -> None:
        # Use the venv python to call the surreal-commands worker module
        # directly — no console script or frozen-binary dispatcher needed.
        # cwd is upstream_root for the same reason as the API.
        args = [
            str(self.venv_python), "-m", "surreal_commands.cli.worker",
            "--import-modules", "commands",
        ]
        self._spawn(args, cwd=self.upstream_root, name="worker")

    def _spawn_next(self, port: int) -> None:
        node_bin = self.bin_dir / f"node-{self.node_arch}" / (
            "node.exe" if self.node_arch.startswith("windows") else "bin/node"
        )
        # The standalone build produces server.js with everything inlined.
        # PORT comes from session_env (Next.js convention).
        self._spawn(
            [str(node_bin), "server.js"],
            cwd=self.repo_root / "frontend",
            name="next",
        )

    def _progress(self, step: str, status: str, message: str = "") -> None:
        if self.progress is not None:
            try:
                self.progress.publish(step, status, message)
            except Exception:
                pass

    def _spawn_llamacpp_embed(self, port: int) -> None:
        if self.nomic_embed_path is None or not self.nomic_embed_path.exists():
            return  # silently skip; embeddings just won't work this session
        args = [
            str(self.venv_python), "-m", "llama_cpp.server",
            "--model", str(self.nomic_embed_path),
            "--host", "127.0.0.1", "--port", str(port),
            "--embedding", "true",
        ]
        self._spawn(args, cwd=self.upstream_root, name="llamacpp_embed")

    def _spawn_whisper(self, port: int) -> None:
        if self.whisper_model_path is None:
            return
        args = [
            str(self.venv_python), "-m", "desktop_shims.whisper_shim",
            "--host", "127.0.0.1", "--port", str(port),
            "--model", str(self.whisper_model_path),
        ]
        self._spawn(args, cwd=self.upstream_root, name="whisper")

    def _spawn_piper(self, port: int) -> None:
        if not self.piper_voices:
            return
        voice_args = []
        for name, path in self.piper_voices.items():
            if path.exists():
                voice_args.extend(["--voice", f"{name}={path}"])
        if not voice_args:
            return
        args = [
            str(self.venv_python), "-m", "desktop_shims.piper_shim",
            "--host", "127.0.0.1", "--port", str(port),
        ] + voice_args
        self._spawn(args, cwd=self.upstream_root, name="piper")

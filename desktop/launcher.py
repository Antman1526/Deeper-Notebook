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
from typing import IO

import httpx

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
        self._procs: list[subprocess.Popen] = []
        self._log_files: list[IO[bytes]] = []
        self.session_env: dict[str, str] = {}
        self.frontend_url: str = ""

    def start_all(self) -> None:
        surreal_port, api_port, frontend_port = find_free_ports(3)

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
            "NEXT_PUBLIC_API_BASE": f"http://127.0.0.1:{api_port}",
        }

        self._spawn_surreal(surreal_port)
        _wait_tcp("127.0.0.1", surreal_port, timeout=15)

        self._spawn_api(api_port)
        _wait_http(f"http://127.0.0.1:{api_port}/health", timeout=30)

        self._spawn_worker()
        # Worker has no port; just give it a beat to subscribe.
        time.sleep(0.5)

        self._spawn_next(frontend_port)
        _wait_http(f"http://127.0.0.1:{frontend_port}/", timeout=60)
        self.frontend_url = f"http://127.0.0.1:{frontend_port}/"

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
        self._spawn(
            [
                str(binary), "start",
                "--user", self.cfg.surreal_user,
                "--pass", self.cfg.surreal_password,
                "--bind", f"127.0.0.1:{port}",
                f"file://{data_dir}",
            ],
            name="surreal",
        )

    def _spawn_api(self, port: int) -> None:
        self._spawn(
            [sys.executable, "-m", "uvicorn", "api.app:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=self.repo_root,
            name="api",
        )

    def _spawn_worker(self) -> None:
        # Upstream uses `surreal-commands` as the worker runtime; the worker
        # discovers commands via the same SURREAL_* env vars.
        self._spawn(
            [sys.executable, "-m", "surreal_commands.worker"],
            cwd=self.repo_root,
            name="worker",
        )

    def _spawn_next(self, port: int) -> None:
        node_bin = self.bin_dir / f"node-{self.node_arch}" / (
            "node.exe" if self.node_arch.startswith("windows") else "bin/node"
        )
        self._spawn(
            [str(node_bin), "start-server.js"],
            cwd=self.repo_root / "frontend",
            name="next",
        )

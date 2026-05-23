"""Process supervisor for the desktop app.

Starts SurrealDB, FastAPI (uvicorn), the open-notebook worker, and the Next.js
frontend in dependency order. Each child gets the per-session env (DB creds,
ports, model provider). Window code (window.py) opens once frontend_url returns
HTTP 200.
"""
from __future__ import annotations

import logging
import os
import signal
import re
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
from desktop.paths import user_home
from desktop.ports import find_free_ports

# v0.6.5 — debugging supervised-child failures was painful: every optional
# service had `except Exception: pass`, so a misconfigured Piper voice path
# (or a missing whisper binary, or an OOM-killed llama.cpp) produced only
# "supervisor.piper: error" in the UI with zero log trail. Now we log the
# exception at warning level AND surface the message through the progress
# bus so the wizard's status overlay can show it.
log = logging.getLogger(__name__)


def _wait_tcp(
    host: str,
    port: int,
    timeout: float = 30.0,
    proc: "subprocess.Popen | None" = None,
) -> None:
    """v0.7.188 — Added optional `proc` arg for early-exit on dead child.
    Pre-fix, if the spawned process crashed at startup (binary missing,
    port collision after our SO_REUSEADDR test), `_wait_tcp` waited the
    full `timeout` seconds before raising. The user stared at "Starting
    SurrealDB…" for up to 30s when the failure was visible in
    `proc.returncode` within 100ms.

    With `proc` passed in, we poll() between probes — a non-None
    returncode means the child exited and there is NO chance the port
    will ever come up. Raise immediately with the child's exit code
    so the launcher can surface a useful error."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(
                f"child for {host}:{port} exited rc={proc.returncode} "
                f"before the port came up — check the per-child log "
                f"in the debug-mode logs dir"
            )
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"tcp {host}:{port} never came up within {timeout}s")


def _wait_http(
    url: str,
    timeout: float = 60.0,
    proc: "subprocess.Popen | None" = None,
) -> None:
    """v0.7.188 — Same early-exit-on-dead-child treatment as _wait_tcp.
    Without it, `_wait_http("/readyz", timeout=180)` would wait 3
    minutes on a uvicorn binary that crashed in 200ms."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(
                f"child for {url} exited rc={proc.returncode} before "
                f"the endpoint became reachable — check the per-child "
                f"log in the debug-mode logs dir"
            )
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
        chat_llm_path: Path | None = None,
        openchronicle_available: bool = False,
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
            user_home()
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
        # v0.7.58 — track drainer threads so stop_all can join them
        # BEFORE closing the log files they're writing into. Without
        # the join, daemon=True meant the OS reaped them at process
        # exit without waiting — but if any line was mid-write at the
        # moment we closed the log file, that buffered tail (often the
        # crash cause) was lost or corrupted. A 1-2s join window is
        # plenty given the drain loop is just iter(readline).
        self._drain_threads: list[threading.Thread] = []
        self.session_env: dict[str, str] = {}
        self.frontend_url: str = ""
        self.embed_port: int = 0
        self.whisper_port: int = 0
        self.piper_port: int = 0
        self.chat_llm_path = chat_llm_path
        self.openchronicle_available = openchronicle_available
        # New v0.4 ports — initialised to 0 so auto_register can skip cleanly
        # when a server failed to start.
        self.chat_llm_port: int = 0
        self.memory_port: int = 0
        self.openchronicle_port: int = 0

    def start_all(self) -> None:
        # v0.7.142 — Singleton enforcement + orphan reaper.
        # Before this release, double-clicking the .app twice spawned two
        # complete process trees with independent dynamic ports. The user
        # would end up with multiple "Unable to Connect" browser windows,
        # each attached to a zombie launcher whose API had since been
        # overwritten. See desktop/singleton.py docstring for the full
        # incident.
        #
        # Now: acquire a PID-file lock at start. If another live instance
        # holds it, AlreadyRunning propagates up to the app's UI which
        # can show a friendly "Open Notebook Plus is already running"
        # dialog. Then sweep any orphans from prior crashed launchers
        # before we bind our own ports.
        from desktop.singleton import (
            acquire_singleton,
            default_pid_file,
            reap_orphans,
        )
        self._singleton = acquire_singleton(default_pid_file())
        # Best-effort orphan reap. The bundle paths cover the two places
        # our subprocess children live: the user-data venv (Python API +
        # worker) and the bundled binary dir (Node, surreal, llama-cpp).
        bundle_paths = [
            Path.home() / ".open-notebook-plus" / "venv",
            self.bin_dir,
        ]
        try:
            orphans = reap_orphans(bundle_paths=bundle_paths)
            if orphans:
                log.warning(
                    "Reaped %d orphaned process(es) from prior launch",
                    len(orphans),
                )
                # Give the OS a moment to actually free the ports they
                # were holding so find_free_ports below doesn't race
                # against zombies clinging to them.
                time.sleep(0.5)
        except Exception as exc:
            # Reap is best-effort — never let a scan failure block boot.
            log.debug("Orphan reap failed (non-fatal): %s", exc)

        (surreal_port, api_port, frontend_port,
         embed_port, whisper_port, piper_port,
         chat_llm_port, memory_port, openchronicle_port) = find_free_ports(9)

        api_url = f"http://127.0.0.1:{api_port}"
        # v0.7.147 — Pin DATA_FOLDER to a per-user, ALWAYS-writable absolute
        # path. open_notebook/config.py used to hardcode "./data" (CWD-
        # relative) and the API subprocess inherits cwd=upstream_root, which
        # is read-only when the .app is launched from a mounted DMG. The
        # resulting EROFS at module import crashed uvicorn before /readyz
        # ever came up, the launcher waited 180s, then exited silently.
        # Injecting an absolute path here makes the launch path resilient
        # to ANY read-only CWD (DMG, Time Machine snapshot, /Applications
        # under a non-admin user, …) without affecting Docker / dev where
        # the env var would simply not be set otherwise.
        data_folder = Path(
            str(user_home())
        ) / ".open-notebook-plus" / "data"
        data_folder.mkdir(parents=True, exist_ok=True)
        self.session_env = {
            **os.environ,
            **self.extra_env,
            "DATA_FOLDER": str(data_folder),
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
            # v0.4 memory layer: predeclare URLs so the surreal-commands worker
            # (spawned before these servers actually bind) sees them in its env.
            # The real servers come up later in start_all; worker connects
            # lazily on first command invocation.
            "MEMORY_CHAT_LLM_URL": f"http://127.0.0.1:{chat_llm_port}/v1",
            "MEMORY_EMBED_URL": f"http://127.0.0.1:{embed_port}/v1",
            "MEMORY_SURREAL_URL": f"ws://127.0.0.1:{surreal_port}/rpc",
        }

        self._progress("supervisor.surreal", "running")
        self._spawn_surreal(surreal_port)
        # v0.7.188 — pass the just-spawned proc to _wait_tcp so the
        # probe can early-exit if the child dies before binding.
        # self._procs[-1] is the latest Popen pushed by _spawn().
        _wait_tcp(
            "127.0.0.1", surreal_port, timeout=30,
            proc=self._procs[-1] if self._procs else None,
        )
        self._progress("supervisor.surreal", "done")

        self._progress("supervisor.api", "running")
        self._spawn_api(api_port)
        # First-launch SurrealDB schema migrations + the heavy upstream import
        # chain (langchain + langgraph + podcast_creator) take 20-60 s before
        # uvicorn finishes startup. Subsequent launches are much faster but
        # we leave the generous timeout in place — better to wait than to
        # tear down an API that was about to come up.
        #
        # v0.7.24 — wait on /readyz, not /health. /health (preserved for
        # back-compat) returns 200 the instant uvicorn binds, even
        # mid-migration. /readyz only returns 200 once the DB is
        # actually reachable AND migrations have applied — the real
        # signal that downstream services (worker, frontend window)
        # can safely come up against the API.
        # v0.7.188 — pass the API proc so 3-minute wait → fail-fast on
        # a uvicorn that crashed in 200ms (binary missing, port
        # collision, EACCES on logging dir, etc.).
        _wait_http(
            f"http://127.0.0.1:{api_port}/readyz", timeout=180,
            proc=self._procs[-1] if self._procs else None,
        )
        self._progress("supervisor.api", "done")

        self._progress("supervisor.worker", "running")
        self._spawn_worker()
        # Worker has no port; just give it a beat to subscribe.
        time.sleep(0.5)
        self._progress("supervisor.worker", "done")

        # v0.7.143 — Patch Next.js standalone build to use the launcher's
        # dynamic API port. The rewrites destination is baked at BUILD
        # time pointing at `localhost:5055`; without this patch, every
        # /api/* request the frontend makes gets proxied to a port that
        # doesn't exist and the user sees "API config endpoint returned
        # status 500" with no API actually broken. See
        # desktop/next_rewrites_patcher.py for the full incident write-up.
        from desktop.next_rewrites_patcher import (
            patch_rewrites_for_api_port,
            PatchError,
        )
        next_cwd = self.repo_root / "frontend"
        try:
            next_cwd = patch_rewrites_for_api_port(next_cwd, api_port)
        except PatchError as exc:
            # Logging not raising — the launcher should keep trying;
            # the user will get the same 500-on-/api/config error
            # screen as before, which now includes a clearer error.
            log.error(
                "Could not patch Next.js rewrites for api_port=%d: %s. "
                "Frontend will likely fail to reach the API.",
                api_port, exc,
            )

        self._progress("supervisor.next", "running")
        self._spawn_next(frontend_port, next_cwd=next_cwd)
        # v0.7.188 — same early-exit pattern as the API wait above.
        _wait_http(
            f"http://127.0.0.1:{frontend_port}/", timeout=120,
            proc=self._procs[-1] if self._procs else None,
        )
        self.frontend_url = f"http://127.0.0.1:{frontend_port}/"
        self._progress("supervisor.next", "done")

        # v0.6.5 — replace 6 copy-pasted try/except blocks with one helper
        # that logs + reports through _progress. Avoids the silent-swallow
        # bug that made debugging missing/broken optional services painful.
        self._try_spawn("supervisor.llamacpp_embed", self._spawn_llamacpp_embed, embed_port)
        self._try_spawn("supervisor.whisper", self._spawn_whisper, whisper_port)
        self._try_spawn("supervisor.piper", self._spawn_piper, piper_port)

        # v0.7.197 — Stash ports for auto_register, BUT ONLY if the
        # corresponding spawn actually produced a server.
        #
        # Before: we unconditionally stored the allocated port even
        # when `_spawn_*` early-returned (no nomic embed file, no
        # whisper model, no piper voices). auto_register then registered
        # credentials with `base_url=http://127.0.0.1:<unused_port>/v1`,
        # and the memory_retriever child was started with
        # `--embed-url http://127.0.0.1:<dead_port>/v1` — so the user
        # saw a "Local Embeddings (llama.cpp)" credential in the UI
        # that failed every test, and the first source upload hung
        # because the embed call to the dead port silently timed out.
        #
        # Mirror the early-return conditions in _spawn_llamacpp_embed /
        # _spawn_whisper / _spawn_piper. If the prerequisite is
        # missing, store 0 so downstream code (auto_register,
        # _spawn_memory_retriever) sees "no embed server" instead of
        # "embed server on a port that nothing is listening on".
        embed_alive = (
            self.nomic_embed_path is not None and self.nomic_embed_path.exists()
        )
        whisper_alive = self.whisper_model_path is not None
        # _spawn_piper additionally requires at least one voice path to
        # actually exist on disk (the dict is filtered there too); keep
        # that check in sync to avoid the same false-port-stash trap.
        piper_alive = bool(self.piper_voices) and any(
            p.exists() for p in self.piper_voices.values()
        )
        self.embed_port = embed_port if embed_alive else 0
        self.whisper_port = whisper_port if whisper_alive else 0
        self.piper_port = piper_port if piper_alive else 0

        # v0.4 additions — order matters: chat LLM must be up before the
        # memory retriever boots, because the retriever instantiates
        # mem0.Memory which validates the LLM endpoint at startup.
        self._try_spawn("supervisor.llamacpp_chat", self._spawn_llamacpp_chat, chat_llm_port)
        self.chat_llm_port = chat_llm_port    # assigned before memory_retriever spawn

        self._try_spawn("supervisor.memory", self._spawn_memory_retriever, memory_port)
        self.memory_port = memory_port

        if self.openchronicle_available:
            self._try_spawn(
                "supervisor.openchronicle",
                self._spawn_openchronicle_bridge,
                openchronicle_port,
            )
        self.openchronicle_port = openchronicle_port if self.openchronicle_available else 0

    def stop_all(self) -> None:
        # v0.7.142 — Release the singleton FIRST so a relaunch isn't
        # blocked while we're still tearing down. The singleton release
        # is idempotent (safe even if start_all never ran or already
        # released). atexit also calls release independently, so the
        # only thing this gets us is faster recovery for the "relaunch
        # immediately after Cmd+Q" case.
        singleton = getattr(self, "_singleton", None)
        if singleton is not None:
            try:
                singleton.release()
            except Exception as exc:
                log.debug("singleton release failed: %s", exc)

        # v0.7.58 — log terminate/wait/close failures at debug level
        # instead of swallowing silently. Previously a zombie child
        # that survived terminate() was invisible; the launcher exited
        # "clean" but the OS still had the worker holding the SurrealDB
        # lock, and the next launch failed with a cryptic "address
        # already in use".
        #
        # v0.7.173 — Kill the entire process GROUP (the v0.7.173 spawn
        # uses `start_new_session=True` so each child is its own group
        # leader; sending SIGTERM to the pgid takes out the immediate
        # child PLUS any forked grandchildren in one signal). The bare
        # `p.terminate()` only signalled the immediate child — Next.js
        # grandchildren (`next-server`) reparented to PID 1 and
        # survived past the .app close. Falls back to terminate() if
        # killpg fails (e.g. process already exited, mocked Popen in
        # tests that doesn't have a real pgid).
        for p in reversed(self._procs):
            try:
                pid = getattr(p, "pid", None)
                if pid and sys.platform != "win32":
                    try:
                        # killpg with the LEADER's PID (which equals
                        # the pgid because start_new_session=True).
                        os.killpg(pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError, OSError):
                        # Process already gone, no permission, or pgid
                        # missing (mock). Fall through to terminate().
                        try:
                            p.terminate()
                        except Exception:
                            pass
                elif pid and sys.platform == "win32":
                    # v0.7.185 — was `os.kill(pid, CTRL_BREAK_EVENT)`. That
                    # only works when the target shares a console with us;
                    # a PyInstaller windowed .exe has NO console, so the
                    # signal is silently dropped and grandchildren leak —
                    # exactly the same bug v0.7.173 fixed for POSIX.
                    # `taskkill /F /T /PID` is the Windows equivalent of
                    # `killpg(SIGKILL)` and works without a console.
                    #   /F = force kill, /T = kill subtree (children +
                    #   grandchildren), /PID <n> = target by PID.
                    # Wrapped in subprocess.run with check=False so a
                    # non-existent PID (already-dead process) doesn't
                    # raise — same forgiveness pattern as the POSIX
                    # killpg branch above. Audit finding #3.
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(pid)],
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5,
                        )
                    except Exception:
                        # taskkill missing (sandboxed environment) /
                        # timed out / other failure — fall back to
                        # the soft signal + terminate sequence.
                        try:
                            os.kill(pid, signal.CTRL_BREAK_EVENT)
                        except Exception:
                            try:
                                p.terminate()
                            except Exception:
                                pass
                else:
                    # No real PID (test mock) — fall back to terminate().
                    p.terminate()
            except Exception as exc:
                # v0.7.82 — `getattr(p, "pid", "?")` instead of `p.pid` so
                # mocked process objects in desktop/tests/test_launcher.py
                # don't raise AttributeError during stop_all teardown.
                # Real subprocess.Popen always has .pid; tests that
                # MagicMock(spec=Popen) may not.
                log.debug("terminate pid=%s failed: %s", getattr(p, "pid", "?"), exc)
        deadline = time.monotonic() + 5
        for p in self._procs:
            try:
                remaining = max(0.0, deadline - time.monotonic())
                p.wait(timeout=remaining if remaining > 0 else 0.1)
            except subprocess.TimeoutExpired:
                p.kill()
            except Exception as exc:
                log.debug("wait pid=%s failed: %s", getattr(p, "pid", "?"), exc)
        # Join drainer threads with a short timeout BEFORE closing the
        # log files they're writing into — otherwise the daemon threads
        # could be mid-write when the file handle goes away. Buffered
        # tails of surreal.log / api.log often hold the crash cause.
        for t in self._drain_threads:
            try:
                t.join(timeout=2.0)
            except Exception as exc:
                log.debug("drain-thread join failed: %s", exc)
        for f in self._log_files:
            try:
                f.close()
            except Exception as exc:
                log.debug("log_file close failed: %s", exc)
        self._procs.clear()
        self._log_files.clear()
        self._drain_threads.clear()

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

        # v0.7.173 — Isolate each child into its own process group so
        # `stop_all` can kill the WHOLE subtree (including grandchildren)
        # in one signal. Previously this was a bare `subprocess.Popen`
        # and `stop_all` only sent SIGTERM to the immediate child —
        # grandchildren reparented to PID 1 and survived after the
        # .app window closed. Documented incident: the
        # `next-server (v16.2.6)` orphan zombies the user has seen
        # accumulating between launches (Next.js forks per-request
        # workers; `next-server` is itself a fork of the `node`
        # process we directly spawn). The v0.7.142 `reap_orphans`
        # was a startup sweep, not a shutdown one — so closing the
        # .app still leaked zombies until the next launch.
        #
        # `start_new_session=True` (POSIX) makes the child a process-
        # group leader. `stop_all` below now uses `os.killpg(pgid,
        # SIGTERM)` to kill the whole group atomically.
        # On Windows the equivalent is `creationflags=CREATE_NEW_PROCESS_GROUP`
        # plus `signal.CTRL_BREAK_EVENT`; only POSIX is supported here
        # currently — Windows launcher builds are a future-work item.
        popen_kwargs: dict = {
            "cwd": str(cwd) if cwd else None,
            "env": self.session_env,
            "stdout": stdout,
            "stderr": stderr,
        }
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True
        else:
            # v0.7.185 — was just CREATE_NEW_PROCESS_GROUP. Added
            # CREATE_NO_WINDOW so each child doesn't pop a transient
            # console window (jarring UX from a packaged windowed
            # .app). The process-group flag remains so `taskkill /T`
            # in stop_all can target the whole subtree.
            popen_kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            )

        proc = subprocess.Popen(args, **popen_kwargs)
        self._procs.append(proc)

        if self.debug_mode and proc.stdout is not None and proc.stderr is not None:
            self._start_drainers(proc, name)

        return proc

    def _start_drainers(self, proc: subprocess.Popen, name: str) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_dir / f"{name}.log"
        log_file = open(log_path, "ab", buffering=0)
        self._log_files.append(log_file)

        # P2-HIGH-16 audit fix: scrub known secrets from subprocess output.
        # The Surreal binary, in particular, echoes its CLI flags (including
        # `--pass=...`) to stdout on startup. With debug_mode on, that would
        # land in surreal.log in plaintext.
        secret_pat = re.compile(
            rb"(?i)(--pass=|password[=:]|surreal_password[=:]|encryption_key[=:])"
            rb"([^\s\"']+)"
        )
        def _redact(b: bytes) -> bytes:
            return secret_pat.sub(rb"\1[REDACTED]", b)

        def drain(stream: IO[bytes], prefix: bytes) -> None:
            try:
                for line in iter(stream.readline, b""):
                    try:
                        log_file.write(prefix + _redact(line))
                    except Exception:
                        return
            except Exception:
                return

        for stream, prefix in ((proc.stdout, b"[out] "), (proc.stderr, b"[err] ")):
            t = threading.Thread(
                target=drain, args=(stream, prefix), name=f"drain-{name}", daemon=True
            )
            t.start()
            # v0.7.58 — track for join-before-log-close in stop_all
            self._drain_threads.append(t)

    def _spawn_surreal(self, port: int) -> None:
        ext = ".exe" if self.surreal_arch.startswith("windows") else ""
        binary = self.bin_dir / f"surreal-{self.surreal_arch}{ext}"
        data_dir = user_home() \
            / ".open-notebook-plus" / "surreal_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        # Use --flag=value form so passwords/usernames that happen to start
        # with '-' (a real possibility from secrets.token_urlsafe which uses
        # base64url, where `-` is a valid char) aren't reparsed by clap as
        # a separate short flag like '-4'.
        # v0.7.185 — was f"file://{data_dir}". On POSIX `data_dir`
        # starts with `/`, producing a valid `file:///Users/.../...`
        # URL. On Windows `data_dir` is e.g. `C:\Users\Joe\.open-
        # notebook-plus\surreal_data`, so the f-string produces
        # `file://C:\Users\...` — NOT a valid file: URL. SurrealDB's
        # URL parser reads `C:` as the host, and storage init fails
        # silently or with a confusing error. `Path.as_uri()` is the
        # idiomatic cross-platform builder: returns
        # `file:///C:/Users/...` on Windows, `file:///Users/...` on
        # POSIX. Audit finding #2.
        self._spawn(
            [
                str(binary), "start",
                f"--user={self.cfg.surreal_user}",
                f"--pass={self.cfg.surreal_password}",
                f"--bind=127.0.0.1:{port}",
                data_dir.as_uri(),
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

    def _spawn_next(self, port: int, *, next_cwd: Path | None = None) -> None:
        node_bin = self.bin_dir / f"node-{self.node_arch}" / (
            "node.exe" if self.node_arch.startswith("windows") else "bin/node"
        )
        # The standalone build produces server.js with everything inlined.
        # PORT comes from session_env (Next.js convention).
        #
        # v0.7.143 — `next_cwd` defaults to the bundled frontend dir but
        # the caller may override with a writable copy if the bundle
        # itself is read-only (e.g., installed under /Applications).
        # See next_rewrites_patcher.patch_rewrites_for_api_port.
        if next_cwd is None:
            next_cwd = self.repo_root / "frontend"
        self._spawn(
            [str(node_bin), "server.js"],
            cwd=next_cwd,
            name="next",
        )

    def _progress(self, step: str, status: str, message: str = "") -> None:
        if self.progress is not None:
            try:
                self.progress.publish(step, status, message)
            except Exception:
                pass

    def _try_spawn(self, step: str, fn, *args) -> None:
        """Wrap an optional/best-effort spawn in progress + logging.

        v0.6.5 — Previously each optional service had its own try/except
        that swallowed exceptions silently and only published "error" to
        the progress bus with no message. Anyone debugging "piper doesn't
        work on my machine" had nothing to go on. Now:
          - logger.warning logs the full exception (with traceback)
          - the progress event includes the str(exc) so the UI sees it
          - control flow is unchanged: failure here doesn't crash launcher
        """
        self._progress(step, "running")
        try:
            fn(*args)
            self._progress(step, "done")
        except Exception as exc:
            log.warning("%s spawn failed: %s", step, exc, exc_info=True)
            self._progress(step, "error", str(exc))

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

    def _spawn_llamacpp_chat(self, port: int) -> None:
        """Second llama-server, this one serving a chat-capable GGUF.

        Needed by mem0's writer (extract_turn / summarize_session) for
        Hermes-3-style tool calling. ~5 GB RAM at runtime.
        """
        # v0.7.67 — log a clear warning when we skip rather than
        # silently returning. The previous comment said "memory writer
        # will simply no-op" — true, but the user opening the bundled
        # app with no chat GGUF will then wonder why "memory" features
        # never produce facts. A single WARNING line in the launcher
        # log identifies the cause immediately. Each cause is logged
        # distinctly so the user can act on it (drop a GGUF in the
        # configured path vs. download one).
        if self.chat_llm_path is None:
            log.warning(
                "Skipping llamacpp_chat: no chat GGUF configured "
                "(chat_llm_path is None). Memory writer (fact "
                "extraction + session summaries) will no-op. "
                "Configure a chat model via the launcher config to "
                "enable it."
            )
            return
        if not self.chat_llm_path.exists():
            log.warning(
                "Skipping llamacpp_chat: configured GGUF not found at "
                "%s. Memory writer will no-op. Download a chat-capable "
                "GGUF (e.g. Hermes-3, Qwen2.5-Instruct, Llama-3.2) to "
                "that path to enable it.",
                self.chat_llm_path,
            )
            return
        # v0.7.8 — n_ctx is configurable via env var. Previous hardcoded 8192
        # capped EVERY chat session at 8k tokens regardless of the model's
        # actual capability. Modern local models commonly support much more:
        # Qwen 2.5/3.x at 32k-131k, Hermes-3 at 131k, Mistral-7B at 32k,
        # Llama-3.2 at 131k. The 8k cap also undermined v0.7.4's Studio
        # fix — Studio's combined-context cap is now ~15k tokens, more than
        # the server itself accepted.
        #
        # Default 16384: safe for any modern local model (covers gemma-2-9b
        # and codellama-13b's 8k/16k while leaving comfortable headroom
        # for Hermes/Qwen/Mistral/Llama larger contexts via env override).
        # Constrained-hardware users with low VRAM can lower it via
        # ONP_CHAT_LLM_CTX; capable users with 32k+ models can raise it.
        n_ctx = os.environ.get("ONP_CHAT_LLM_CTX", "16384")
        # Defensive: validate it's a positive int. Garbage falls back to
        # the safe default rather than passing through to llama-cpp.
        try:
            n_ctx_int = int(n_ctx)
            if n_ctx_int < 512:
                log.warning(
                    "ONP_CHAT_LLM_CTX=%s too low (<512); using 16384 instead",
                    n_ctx,
                )
                n_ctx = "16384"
        except ValueError:
            log.warning(
                "ONP_CHAT_LLM_CTX=%r is not an int; using 16384", n_ctx,
            )
            n_ctx = "16384"

        args = [
            str(self.venv_python), "-m", "llama_cpp.server",
            "--model", str(self.chat_llm_path),
            "--host", "127.0.0.1", "--port", str(port),
            "--n_ctx", n_ctx,
        ]
        self._spawn(args, cwd=self.upstream_root, name="llamacpp_chat")

    def _spawn_memory_retriever(self, port: int) -> None:
        args = [
            str(self.venv_python), "-m", "desktop_shims.memory_shim",
            "--host", "127.0.0.1", "--port", str(port),
            "--surreal-url", self.session_env["SURREAL_URL"],
            "--embed-url",
            f"http://127.0.0.1:{self.embed_port}/v1" if self.embed_port else "",
            "--llm-url",
            f"http://127.0.0.1:{self.chat_llm_port}/v1" if self.chat_llm_port else "",
        ]
        self._spawn(args, cwd=self.upstream_root, name="memory")

    def _spawn_openchronicle_bridge(self, port: int) -> None:
        if not self.openchronicle_available:
            return
        # v0.7.197 — Honour OPENCHRONICLE_MCP_URL the same way the shim's
        # argparse default does. Before, the launcher hardcoded
        # `--mcp-url http://127.0.0.1:8742/mcp` on every spawn —
        # which OVERRODE the env-var default in
        # `openchronicle_shim.py`'s argparse. Users running
        # OpenChronicle on a non-default port (the documented use
        # case) couldn't reach it from ONP. The P1-MED-10 audit fix
        # in the shim was dead code as long as this launcher line
        # forced the default URL. Read the env now; fall back to the
        # same default the shim would have used.
        mcp_url = os.environ.get(
            "OPENCHRONICLE_MCP_URL", "http://127.0.0.1:8742/mcp"
        )
        args = [
            str(self.venv_python), "-m", "desktop_shims.openchronicle_shim",
            "--host", "127.0.0.1", "--port", str(port),
            "--mcp-url", mcp_url,
        ]
        self._spawn(args, cwd=self.upstream_root, name="openchronicle")

"""v0.8.67l — Self-healing for SurrealDB live-query corruption.

The surreal-commands worker registers a LIVE query (``db.live("command")``) at
startup. After an UNCLEAN SurrealDB shutdown — SIGKILL, Force Quit, power loss,
or an OOM-kill, anything the graceful ``stop_all`` can't catch — the persisted
live-query bookkeeping in ``surreal_data`` can collide when the next worker
re-registers, and the worker crashes on boot with:

    There was a problem with the database: The key being inserted already exists

which bricks source processing until the DB is repaired. v0.8.67g raised the
shutdown grace to make this rarer; this module makes recovery AUTOMATIC so the
user never has to run ``scripts/repair_desktop_db.sh`` by hand.

Design — safe by construction:

  * A worker watcher (in the launcher) detects the crash signature in
    ``worker.log`` and sets a one-shot flag file. It does NOT repair
    mid-boot: the API is already connected to the live SurrealDB and
    rewriting ``surreal_data`` underneath it would be unsafe.
  * On the NEXT boot, BEFORE SurrealDB starts (clean slate, nothing
    connected), the launcher calls :func:`auto_repair`, which mirrors the
    proven ``scripts/repair_desktop_db.sh``: export → physical copy → move the
    stale dir aside → reimport into a fresh dir. Backup-FIRST, and ABORT-SAFE:
    if the export is empty or the import fails, the original data dir is
    restored and it returns ``False`` (the app boots no worse than before).
  * The flag is cleared after exactly one attempt, so a repair that doesn't
    fix the problem can NEVER cause a boot loop.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

# The worker's crash traceback contains this exact SurrealDB message. Matched
# case-insensitively; kept specific (not a bare "already exists") so unrelated
# log lines never trigger a needless repair.
_LQ_SIGNATURE = "the key being inserted already exists"


def looks_like_lq_corruption(log_text: str) -> bool:
    """True if ``log_text`` shows the live-query "key already exists" crash."""
    if not log_text:
        return False
    return _LQ_SIGNATURE in log_text.lower()


def flag_path(data_home: Path) -> Path:
    return Path(data_home) / ".needs_db_repair"


def needs_repair(data_home: Path) -> bool:
    return flag_path(data_home).exists()


def set_needs_repair(data_home: Path) -> None:
    p = flag_path(data_home)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
    except OSError:
        pass  # best-effort; a missed flag just means manual repair, never a crash


def clear_needs_repair(data_home: Path) -> None:
    try:
        flag_path(data_home).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _wait_surreal_ready(port: int, timeout: float = 40.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=2
            ) as r:
                if getattr(r, "status", r.getcode()) == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def auto_repair(
    *,
    surreal_bin: Path,
    data_dir: Path,
    backup_dir: Path,
    surreal_user: str,
    surreal_password: str,
    ts: str,
    namespace: str = "open_notebook",
    database: str = "open_notebook",
    port: int = 18799,
    log,
) -> bool:
    """Backup-first, abort-safe repair of a corrupted ``surreal_data``.

    Returns True only if a fresh dir was successfully rebuilt from an export.
    On any failure the original data dir is left (or restored) in place and
    False is returned — the caller should boot anyway (degraded), never loop.

    Must be called when NOTHING is connected to the data dir (pre-SurrealDB
    start). Spawns its own throwaway SurrealDB on ``port`` for the export +
    import, mirroring scripts/repair_desktop_db.sh.
    """
    surreal_bin = Path(surreal_bin)
    data_dir = Path(data_dir)
    backup_dir = Path(backup_dir)

    if not surreal_bin.exists():
        log.error(
            "db_repair: surreal binary not found at %s — cannot repair", surreal_bin
        )
        return False
    if not data_dir.exists():
        log.info("db_repair: no surreal_data at %s — nothing to repair", data_dir)
        return False

    backup_dir.mkdir(parents=True, exist_ok=True)
    export = backup_dir / f"surreal-export-{ts}.surql"

    def _start(dir_: Path) -> subprocess.Popen:
        proc = subprocess.Popen(
            [
                str(surreal_bin),
                "start",
                f"--user={surreal_user}",
                f"--pass={surreal_password}",
                f"--bind=127.0.0.1:{port}",
                Path(dir_).as_uri(),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _wait_surreal_ready(port):
            try:
                proc.terminate()
            except Exception:
                pass
            raise RuntimeError(f"temp SurrealDB did not become ready on :{port}")
        return proc

    def _stop(proc: subprocess.Popen) -> None:
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _run(action: str) -> None:
        subprocess.run(
            [
                str(surreal_bin),
                action,
                "--endpoint",
                f"http://127.0.0.1:{port}",
                "--username",
                surreal_user,
                "--password",
                surreal_password,
                "--namespace",
                namespace,
                "--database",
                database,
                str(export),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # 1) Backup FIRST: logical export + physical copy, before touching anything.
    try:
        proc = _start(data_dir)
        try:
            _run("export")
        finally:
            _stop(proc)
    except Exception as exc:
        log.error("db_repair: export step failed (%s) — no changes made", exc)
        return False

    if not export.exists() or export.stat().st_size == 0:
        log.error("db_repair: export came out empty — aborting, no changes made")
        return False

    physbak = backup_dir / f"surreal_data.physbak-{ts}"
    try:
        shutil.copytree(data_dir, physbak)
    except Exception as exc:
        log.error(
            "db_repair: physical backup failed (%s) — aborting, no changes made", exc
        )
        return False

    # 2) Move the stale dir aside (never delete) and 3) import into a fresh dir.
    stale = data_dir.with_name(f"{data_dir.name}.stale-{ts}")
    try:
        data_dir.rename(stale)
    except Exception as exc:
        log.error("db_repair: could not move stale data aside (%s) — aborting", exc)
        return False

    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        proc = _start(data_dir)
        try:
            _run("import")
        finally:
            _stop(proc)
        log.warning(
            "db_repair: SUCCESS. Rebuilt clean DB. Backups: %s , %s ; old DB: %s",
            export,
            physbak,
            stale,
        )
        return True
    except Exception as exc:
        # Abort-safe: restore the original data dir so we're no worse than before.
        log.error("db_repair: import failed (%s) — restoring original data dir", exc)
        try:
            if data_dir.exists():
                shutil.rmtree(data_dir)
            stale.rename(data_dir)
            log.warning("db_repair: original data dir restored from %s", stale)
        except Exception as exc2:
            log.error(
                "db_repair: RESTORE FAILED (%s). Your data is safe at %s (and export %s); "
                "move it back to %s manually.",
                exc2,
                stale,
                export,
                data_dir,
            )
        return False

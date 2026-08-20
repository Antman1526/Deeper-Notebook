# open-notebook-Plus Desktop App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a clickable desktop app of open-notebook (Mac `.dmg`, Windows `.zip`) that wraps the upstream FastAPI + Next.js stack in a PyWebView window, supervises SurrealDB / FastAPI / worker / Next.js / model backend as child processes, prefers local model inference (Ollama → llama.cpp), reads GGUFs from a configurable directory, and is built unsigned via GitHub Actions.

**Architecture:** A Python `launcher.py` script bundled with PyInstaller spawns SurrealDB (bundled binary), the upstream FastAPI uvicorn server, the upstream worker process, the upstream Next.js server (via bundled portable Node.js), and a model backend (Ollama discovery or llama-cpp-python server). Once the Next.js server is healthy, the launcher opens a PyWebView native window pointed at it. All paths and provider preferences live in `~/.open-notebook-plus/config.toml`, written by a first-run wizard (a small aiohttp server serving static HTML inside its own PyWebView window).

**Tech Stack:** Python 3.12, PyWebView, PyInstaller, aiohttp, llama-cpp-python, FastAPI (upstream), Next.js + Node.js 20 (upstream), SurrealDB v2 (bundled binary), GitHub Actions (`macos-14`, `macos-13`, `windows-latest`).

**Spec:** [docs/superpowers/specs/2026-05-09-open-notebook-plus-desktop-design.md](../specs/2026-05-09-open-notebook-plus-desktop-design.md)

---

## File map (created/modified by this plan)

### Created
```
desktop/
├── __init__.py
├── launcher.py
├── window.py
├── config.py
├── ports.py
├── providers/
│   ├── __init__.py
│   ├── ollama.py
│   ├── llamacpp.py
│   ├── paperclip.py
│   └── hermes.py
├── first_run/
│   ├── __init__.py
│   ├── server.py
│   └── static/
│       ├── index.html
│       ├── style.css
│       └── wizard.js
├── resources/
│   ├── icon.icns
│   ├── icon.ico
│   └── splash.html
├── build/
│   ├── runtimes.toml
│   ├── fetch_runtimes.py
│   ├── pyinstaller.spec
│   ├── post_build_mac.sh
│   └── post_build_windows.ps1
├── requirements.txt
├── README.md
└── tests/
    ├── __init__.py
    ├── test_config.py
    ├── test_ports.py
    ├── test_providers.py
    └── test_first_run.py

.github/workflows/build-desktop.yml
```

### Modified
- `README.md` — top-level, full rewrite for the fork
- `.gitignore` — add `desktop/bin/`, `dist/`, `build/` (PyInstaller outputs), `~/.open-notebook-plus/` is outside repo so no-op

### Untouched
The entire upstream tree (`api/`, `frontend/`, `open_notebook/`, `prompts/`, `commands/`, `scripts/`, `tests/`). Upstream merges should remain trivial.

---

## Task 1: Create `desktop/` skeleton + tests harness

**Files:**
- Create: `desktop/__init__.py`, `desktop/tests/__init__.py`, `desktop/tests/test_smoke.py`, `desktop/requirements.txt`, `desktop/README.md`

- [ ] **Step 1: Create empty package init files**

```python
# desktop/__init__.py
"""open-notebook-Plus desktop wrapper. See docs/superpowers/specs/2026-05-09-open-notebook-plus-desktop-design.md."""

__version__ = "0.1.0"
```

```python
# desktop/tests/__init__.py
```

- [ ] **Step 2: Write a smoke test that imports the package**

```python
# desktop/tests/test_smoke.py
import desktop


def test_package_importable():
    assert desktop.__version__ == "0.1.0"
```

- [ ] **Step 3: Pin desktop-only dependencies**

```text
# desktop/requirements.txt
# Pinned for reproducibility; CI installs these on top of the upstream pyproject.toml.
pywebview==5.4
pyinstaller==6.11.1
aiohttp==3.11.10
llama-cpp-python==0.3.5
httpx==0.28.1
tomli==2.2.1; python_version < "3.11"
pytest==8.3.4
pytest-asyncio==0.24.0
```

- [ ] **Step 4: Stub the desktop README**

```markdown
# desktop/

Internals for the open-notebook-Plus desktop wrapper. See
[../docs/superpowers/specs/2026-05-09-open-notebook-plus-desktop-design.md] for design and
[../docs/superpowers/plans/2026-05-09-open-notebook-plus-desktop.md] for the implementation plan.

## Local build (developer)

```
pip install -r desktop/requirements.txt
cd frontend && npm ci && npm run build && cd ..
python desktop/build/fetch_runtimes.py
pyinstaller desktop/build/pyinstaller.spec
```

Output lands in `dist/open-notebook-Plus.app` (Mac) or `dist/open-notebook-Plus/` (Windows).
```

- [ ] **Step 5: Run the smoke test**

Run: `cd /Users/Antman/Desktop/OpenNotebook/open-notebook-Plus && python -m pytest desktop/tests/test_smoke.py -v`
Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add desktop/__init__.py desktop/tests/__init__.py desktop/tests/test_smoke.py \
        desktop/requirements.txt desktop/README.md
git commit -m "desktop: scaffold package, smoke test, pinned deps"
```

---

## Task 2: `desktop/config.py` — TOML config persistence

The launcher and wizard read/write `~/.open-notebook-plus/config.toml`. Keys: `model_dir` (str), `provider` (`"ollama"|"llamacpp"|"none"`), `default_model` (str), `surreal_user`/`surreal_password` (random per-session).

**Files:**
- Create: `desktop/config.py`, `desktop/tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/tests/test_config.py
from pathlib import Path

import pytest

from desktop.config import Config, default_model_dir, load_or_create


def test_default_model_dir_macos(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_model_dir() == tmp_path / "Desktop" / "AI_Models"


def test_default_model_dir_windows(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert default_model_dir() == tmp_path / "Desktop" / "AI_Models"


def test_load_or_create_writes_default_when_missing(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg = load_or_create(cfg_path)
    assert cfg_path.exists()
    assert cfg.model_dir.is_absolute()
    assert cfg.provider == "none"
    assert cfg.default_model == ""
    assert len(cfg.surreal_password) >= 24


def test_load_or_create_reads_existing(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        'model_dir = "/tmp/foo"\n'
        'provider = "ollama"\n'
        'default_model = "llama3.1"\n'
        'surreal_user = "root"\n'
        'surreal_password = "supersecretsupersecret"\n'
    )
    cfg = load_or_create(cfg_path)
    assert cfg.model_dir == Path("/tmp/foo")
    assert cfg.provider == "ollama"
    assert cfg.default_model == "llama3.1"
    assert cfg.surreal_password == "supersecretsupersecret"


def test_save_round_trips(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg = Config(
        model_dir=tmp_path / "AI",
        provider="llamacpp",
        default_model="x.gguf",
        surreal_user="root",
        surreal_password="ABCDEFGHIJKLMNOPQRSTUVWX",
    )
    cfg.save(cfg_path)
    loaded = load_or_create(cfg_path)
    assert loaded == cfg


def test_invalid_provider_raises(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        'model_dir = "/tmp"\nprovider = "bogus"\n'
        'default_model = ""\nsurreal_user = "root"\n'
        'surreal_password = "AAAAAAAAAAAAAAAAAAAAAAAA"\n'
    )
    with pytest.raises(ValueError, match="provider"):
        load_or_create(cfg_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest desktop/tests/test_config.py -v`
Expected: All FAIL with `ModuleNotFoundError: No module named 'desktop.config'`.

- [ ] **Step 3: Implement `desktop/config.py`**

```python
# desktop/config.py
"""Config persistence for the desktop launcher and first-run wizard."""

from __future__ import annotations

import os
import secrets
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Provider = Literal["ollama", "llamacpp", "none"]
_VALID_PROVIDERS: set[str] = {"ollama", "llamacpp", "none"}


@dataclass(frozen=True)
class Config:
    model_dir: Path
    provider: Provider
    default_model: str
    surreal_user: str
    surreal_password: str

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["model_dir"] = str(self.model_dir)
        toml = "".join(f'{k} = "{v}"\n' for k, v in data.items())
        path.write_text(toml)


def default_model_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["USERPROFILE"]) / "Desktop" / "AI_Models"
    return Path(os.environ["HOME"]) / "Desktop" / "AI_Models"


def default_config_path() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["USERPROFILE"]) / ".open-notebook-plus" / "config.toml"
    return Path(os.environ["HOME"]) / ".open-notebook-plus" / "config.toml"


def load_or_create(path: Path) -> Config:
    if not path.exists():
        cfg = Config(
            model_dir=default_model_dir(),
            provider="none",
            default_model="",
            surreal_user="root",
            surreal_password=secrets.token_urlsafe(24),
        )
        cfg.save(path)
        return cfg

    raw = tomllib.loads(path.read_text())
    provider = raw.get("provider", "none")
    if provider not in _VALID_PROVIDERS:
        raise ValueError(f"Invalid provider in {path}: {provider!r}")
    return Config(
        model_dir=Path(raw["model_dir"]),
        provider=provider,  # type: ignore[arg-type]
        default_model=raw.get("default_model", ""),
        surreal_user=raw.get("surreal_user", "root"),
        surreal_password=raw["surreal_password"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest desktop/tests/test_config.py -v`
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/config.py desktop/tests/test_config.py
git commit -m "desktop: config.py with TOML round-trip and platform defaults"
```

---

## Task 3: `desktop/ports.py` — free localhost port discovery

**Files:**
- Create: `desktop/ports.py`, `desktop/tests/test_ports.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/tests/test_ports.py
import socket

from desktop.ports import find_free_port, find_free_ports


def test_find_free_port_returns_open_port():
    port = find_free_port()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", port))
    s.close()


def test_find_free_ports_returns_distinct():
    ports = find_free_ports(4)
    assert len(set(ports)) == 4
    for p in ports:
        assert 1024 < p < 65536


def test_find_free_ports_zero_returns_empty():
    assert find_free_ports(0) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest desktop/tests/test_ports.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `desktop/ports.py`**

```python
# desktop/ports.py
"""Free localhost port discovery."""

from __future__ import annotations

import socket
from contextlib import ExitStack


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_free_ports(n: int) -> list[int]:
    """Allocate n distinct free ports atomically (sockets held until return)."""
    if n == 0:
        return []
    with ExitStack() as stack:
        socks = [
            stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            for _ in range(n)
        ]
        for s in socks:
            s.bind(("127.0.0.1", 0))
        return [s.getsockname()[1] for s in socks]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest desktop/tests/test_ports.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/ports.py desktop/tests/test_ports.py
git commit -m "desktop: free-port discovery with atomic multi-port allocation"
```

---

## Task 4: `desktop/build/runtimes.toml` + `fetch_runtimes.py`

Pins SurrealDB and Node.js versions; downloads binaries into `desktop/bin/` for PyInstaller to bundle.

**Files:**
- Create: `desktop/build/__init__.py`, `desktop/build/runtimes.toml`, `desktop/build/fetch_runtimes.py`
- Modify: `.gitignore` — add `desktop/bin/`

- [ ] **Step 1: Pin runtime versions**

```toml
# desktop/build/runtimes.toml
[surrealdb]
version = "2.1.0"

[surrealdb.urls]
darwin-arm64 = "https://github.com/surrealdb/surrealdb/releases/download/v2.1.0/surreal-v2.1.0.darwin-arm64.tgz"
darwin-x86_64 = "https://github.com/surrealdb/surrealdb/releases/download/v2.1.0/surreal-v2.1.0.darwin-amd64.tgz"
windows-x86_64 = "https://github.com/surrealdb/surrealdb/releases/download/v2.1.0/surreal-v2.1.0.windows-amd64.exe"

[node]
version = "20.18.0"

[node.urls]
darwin-arm64 = "https://nodejs.org/dist/v20.18.0/node-v20.18.0-darwin-arm64.tar.gz"
darwin-x86_64 = "https://nodejs.org/dist/v20.18.0/node-v20.18.0-darwin-x64.tar.gz"
windows-x86_64 = "https://nodejs.org/dist/v20.18.0/node-v20.18.0-win-x64.zip"
```

- [ ] **Step 2: Update `.gitignore`**

Append to existing `.gitignore`:

```
# desktop wrapper build outputs
desktop/bin/
dist/
build/
*.spec.bak
```

- [ ] **Step 3: Write the fetch script**

```python
# desktop/build/__init__.py
```

```python
# desktop/build/fetch_runtimes.py
"""Download pinned SurrealDB + Node.js runtimes into desktop/bin/ for the host platform."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "desktop" / "bin"
RUNTIMES = ROOT / "desktop" / "build" / "runtimes.toml"


def host_arch() -> str:
    """Return the canonical key matching runtimes.toml URL rows."""
    sys_plat = sys.platform
    machine = platform.machine().lower()
    if sys_plat == "darwin":
        return "darwin-arm64" if machine in ("arm64", "aarch64") else "darwin-x86_64"
    if sys_plat == "win32":
        return "windows-x86_64"
    raise RuntimeError(f"Unsupported platform: {sys_plat}/{machine}")


def download(url: str, dest: Path) -> None:
    print(f"  downloading {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as r, dest.open("wb") as f:
        shutil.copyfileobj(r, f)


def fetch_surreal(version: str, url: str, arch: str) -> None:
    BIN.mkdir(parents=True, exist_ok=True)
    if arch.startswith("windows"):
        out = BIN / f"surreal-{arch}.exe"
        download(url, out)
    else:
        archive = BIN / "surreal.tgz"
        download(url, archive)
        with tarfile.open(archive) as t:
            t.extract("surreal", path=BIN)
        archive.unlink()
        (BIN / "surreal").rename(BIN / f"surreal-{arch}")
        (BIN / f"surreal-{arch}").chmod(0o755)
    print(f"  surreal v{version} → {BIN}/surreal-{arch}")


def fetch_node(version: str, url: str, arch: str) -> None:
    out_dir = BIN / f"node-{arch}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    if arch.startswith("windows"):
        archive = BIN / "node.zip"
        download(url, archive)
        with zipfile.ZipFile(archive) as z:
            z.extractall(BIN)
        # Node win zip extracts to node-vX.Y.Z-win-x64/
        extracted = next(BIN.glob(f"node-v{version}-*"))
        extracted.rename(out_dir)
        archive.unlink()
    else:
        archive = BIN / "node.tar.gz"
        download(url, archive)
        with tarfile.open(archive) as t:
            t.extractall(BIN)
        extracted = next(BIN.glob(f"node-v{version}-*"))
        extracted.rename(out_dir)
        archive.unlink()
    print(f"  node v{version} → {out_dir}")


def main() -> int:
    arch = host_arch()
    cfg = tomllib.loads(RUNTIMES.read_text())
    print(f"Fetching runtimes for {arch}")
    fetch_surreal(cfg["surrealdb"]["version"], cfg["surrealdb"]["urls"][arch], arch)
    fetch_node(cfg["node"]["version"], cfg["node"]["urls"][arch], arch)

    # Sanity check
    surreal = BIN / (
        f"surreal-{arch}.exe" if arch.startswith("windows") else f"surreal-{arch}"
    )
    node_bin = (
        BIN
        / f"node-{arch}"
        / ("node.exe" if arch.startswith("windows") else "bin/node")
    )
    print(f"\nVerifying:")
    print(f"  surreal: {surreal} ({surreal.stat().st_size // 1024 // 1024} MB)")
    print(f"  node:    {node_bin} ({node_bin.stat().st_size // 1024 // 1024} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the script locally for the current host**

Run: `cd /Users/Antman/Desktop/OpenNotebook/open-notebook-Plus && python desktop/build/fetch_runtimes.py`
Expected: prints `darwin-arm64`, downloads ~80 MB Node + ~25 MB SurrealDB into `desktop/bin/`, ends with verifying paths.

- [ ] **Step 5: Smoke-test the binaries**

Run:
```bash
desktop/bin/surreal-darwin-arm64 version
desktop/bin/node-darwin-arm64/bin/node --version
```
Expected: SurrealDB version string and `v20.18.0`.

- [ ] **Step 6: Commit (without `desktop/bin/`)**

```bash
git add desktop/build/__init__.py desktop/build/runtimes.toml \
        desktop/build/fetch_runtimes.py .gitignore
git commit -m "desktop: pin Surreal v2.1.0 + Node v20.18.0 runtimes, add fetch script"
```

---

## Task 5: `desktop/providers/__init__.py` — Provider Protocol

**Files:**
- Create: `desktop/providers/__init__.py`, `desktop/tests/test_providers_protocol.py`

- [ ] **Step 1: Write the failing test**

```python
# desktop/tests/test_providers_protocol.py
from desktop.providers import ModelProvider, ProviderEnv, ProviderError


def test_provider_env_is_dict_subclass():
    env = ProviderEnv(API_KEY="x", BASE_URL="http://localhost:1234")
    assert env["API_KEY"] == "x"
    assert isinstance(env, dict)


def test_provider_protocol_attrs_present():
    # The Protocol itself defines `name`, `is_available`, `list_models`, `start`, `stop`.
    assert hasattr(ModelProvider, "name")
    assert callable(getattr(ModelProvider, "is_available", None))
    assert callable(getattr(ModelProvider, "list_models", None))
    assert callable(getattr(ModelProvider, "start", None))
    assert callable(getattr(ModelProvider, "stop", None))


def test_provider_error_subclass_of_runtimeerror():
    with __import__("pytest").raises(RuntimeError):
        raise ProviderError("boom")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest desktop/tests/test_providers_protocol.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the Protocol**

```python
# desktop/providers/__init__.py
"""Pluggable model-backend interface used by the launcher.

Each provider knows how to detect availability, list models, and (for backends
that need a process) spawn one and yield env vars to inject into the upstream
FastAPI process so existing langchain integrations Just Work.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class ProviderError(RuntimeError):
    """Raised by provider methods on detection or startup failure."""


class ProviderEnv(dict[str, str]):
    """Environment variables to inject into the upstream FastAPI process."""


@runtime_checkable
class ModelProvider(Protocol):
    name: str

    def is_available(self) -> bool: ...
    def list_models(self) -> list[str]: ...
    def start(self, model: str) -> ProviderEnv: ...
    def stop(self) -> None: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest desktop/tests/test_providers_protocol.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/providers/__init__.py desktop/tests/test_providers_protocol.py
git commit -m "desktop: ModelProvider Protocol + ProviderEnv container"
```

---

## Task 6: `desktop/providers/ollama.py` — Ollama discovery

Ollama auto-starts as a system daemon on most installs. We never spawn it; we just detect and list its models.

**Files:**
- Create: `desktop/providers/ollama.py`, `desktop/tests/test_ollama_provider.py`

- [ ] **Step 1: Write the failing tests (httpx-mock)**

```python
# desktop/tests/test_ollama_provider.py
import httpx
import pytest

from desktop.providers import ProviderEnv
from desktop.providers.ollama import OllamaProvider


@pytest.fixture
def provider():
    return OllamaProvider(base_url="http://127.0.0.1:11434")


def test_is_available_true_when_endpoint_responds(provider, monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *a, **kw: httpx.Response(200, json={"models": []})
    )
    assert provider.is_available() is True


def test_is_available_false_when_endpoint_unreachable(provider, monkeypatch):
    def raise_(*a, **kw):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(httpx, "get", raise_)
    assert provider.is_available() is False


def test_list_models_returns_names(provider, monkeypatch):
    payload = {"models": [{"name": "llama3.1:latest"}, {"name": "mistral:7b"}]}
    monkeypatch.setattr(
        httpx, "get", lambda *a, **kw: httpx.Response(200, json=payload)
    )
    assert provider.list_models() == ["llama3.1:latest", "mistral:7b"]


def test_start_returns_env_with_base_url_and_model(provider):
    env = provider.start("llama3.1:latest")
    assert isinstance(env, ProviderEnv)
    assert env["OLLAMA_BASE_URL"] == "http://127.0.0.1:11434"
    assert env["DEFAULT_MODEL"] == "llama3.1:latest"


def test_stop_is_noop(provider):
    provider.stop()  # should not raise; Ollama is daemon-managed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest desktop/tests/test_ollama_provider.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement OllamaProvider**

```python
# desktop/providers/ollama.py
"""Ollama provider: detection + model listing only. Ollama daemon is user-managed."""

from __future__ import annotations

import httpx

from desktop.providers import ProviderEnv


class OllamaProvider:
    name: str = "ollama"

    def __init__(
        self, base_url: str = "http://127.0.0.1:11434", timeout: float = 1.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=self.timeout)
            return r.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            return False

    def list_models(self) -> list[str]:
        r = httpx.get(f"{self.base_url}/api/tags", timeout=self.timeout)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    def start(self, model: str) -> ProviderEnv:
        return ProviderEnv(
            OLLAMA_BASE_URL=self.base_url,
            DEFAULT_MODEL=model,
        )

    def stop(self) -> None:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest desktop/tests/test_ollama_provider.py -v`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/providers/ollama.py desktop/tests/test_ollama_provider.py
git commit -m "desktop: OllamaProvider with detection, listing, env-injection"
```

---

## Task 7: `desktop/providers/llamacpp.py` — llama-cpp-python supervisor

Scans the configured GGUF directory recursively, lists models, and on `start()` spawns `python -m llama_cpp.server --model <path> --host 127.0.0.1 --port <free>`. One model loaded at a time.

**Files:**
- Create: `desktop/providers/llamacpp.py`, `desktop/tests/test_llamacpp_provider.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/tests/test_llamacpp_provider.py
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from desktop.providers import ProviderEnv
from desktop.providers.llamacpp import LlamaCppProvider


@pytest.fixture
def gguf_dir(tmp_path: Path) -> Path:
    (tmp_path / "a" / "nested").mkdir(parents=True)
    (tmp_path / "a" / "nested" / "model_a.gguf").write_bytes(b"x" * (2 * 1024 * 1024))
    (tmp_path / "model_b.gguf").write_bytes(b"x" * (3 * 1024 * 1024))
    (tmp_path / "ignore_me.txt").write_text("nope")
    return tmp_path


def test_is_available_true_when_dir_has_gguf(gguf_dir):
    p = LlamaCppProvider(model_dir=gguf_dir)
    assert p.is_available() is True


def test_is_available_false_when_no_gguf(tmp_path):
    p = LlamaCppProvider(model_dir=tmp_path)
    assert p.is_available() is False


def test_list_models_returns_relative_paths_sorted(gguf_dir):
    p = LlamaCppProvider(model_dir=gguf_dir)
    assert p.list_models() == ["a/nested/model_a.gguf", "model_b.gguf"]


def test_list_models_skips_stub_files(gguf_dir):
    (gguf_dir / "stub.gguf").write_bytes(b"x" * 100)  # < 1 MB
    p = LlamaCppProvider(model_dir=gguf_dir)
    assert "stub.gguf" not in p.list_models()


def test_start_spawns_server_and_returns_env(gguf_dir, monkeypatch):
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: fake_proc)
    monkeypatch.setattr("desktop.providers.llamacpp.find_free_port", lambda: 51111)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    p = LlamaCppProvider(model_dir=gguf_dir, ready_probe=lambda port: True)
    env = p.start("model_b.gguf")
    assert isinstance(env, ProviderEnv)
    # Upstream uses esperanto's openai_compatible provider; env vars confirmed
    # by reading esperanto/providers/llm/openai_compatible.py.
    assert env["OPENAI_COMPATIBLE_BASE_URL"] == "http://127.0.0.1:51111/v1"
    assert env["OPENAI_COMPATIBLE_API_KEY"] == "sk-no-key"
    p.stop()
    fake_proc.terminate.assert_called_once()


def test_start_raises_if_model_missing(tmp_path):
    p = LlamaCppProvider(model_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        p.start("does_not_exist.gguf")


def test_start_raises_if_server_never_ready(gguf_dir, monkeypatch):
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = None
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: fake_proc)
    monkeypatch.setattr("desktop.providers.llamacpp.find_free_port", lambda: 51112)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    p = LlamaCppProvider(
        model_dir=gguf_dir, ready_probe=lambda port: False, max_wait=0.01
    )
    with pytest.raises(RuntimeError, match="ready"):
        p.start("model_b.gguf")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest desktop/tests/test_llamacpp_provider.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement LlamaCppProvider**

```python
# desktop/providers/llamacpp.py
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
        return (
            httpx.get(f"http://127.0.0.1:{port}/v1/models", timeout=0.5).status_code
            == 200
        )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        return False


class LlamaCppProvider:
    name: str = "llamacpp"

    def __init__(
        self,
        model_dir: Path,
        ready_probe: Callable[[int], bool] = _http_ready,
        max_wait: float = 60.0,
    ) -> None:
        self.model_dir = model_dir
        self._ready_probe = ready_probe
        self._max_wait = max_wait
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
            [
                sys.executable,
                "-m",
                "llama_cpp.server",
                "--model",
                str(path),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._port = port

        deadline = time.monotonic() + self._max_wait
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"llama_cpp.server exited prematurely "
                    f"(returncode={self._proc.returncode})"
                )
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

    def _iter_ggufs(self):
        if not self.model_dir.exists():
            return
        for p in self.model_dir.rglob("*.gguf"):
            if p.is_file() and p.stat().st_size >= MIN_GGUF_BYTES:
                yield p
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest desktop/tests/test_llamacpp_provider.py -v`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/providers/llamacpp.py desktop/tests/test_llamacpp_provider.py
git commit -m "desktop: LlamaCppProvider with GGUF discovery + lifecycle-managed server"
```

---

## Task 8: `desktop/providers/paperclip.py` — Phase 2 stub

**Files:**
- Create: `desktop/providers/paperclip.py`, append to `desktop/tests/test_providers_protocol.py`

- [ ] **Step 1: Write the failing test**

Append to `desktop/tests/test_providers_protocol.py`:

```python
# (append at end)
from desktop.providers.paperclip import PaperclipProvider


def test_paperclip_provider_is_phase2_stub():
    p = PaperclipProvider()
    assert p.name == "paperclip"
    assert p.is_available() is False
    with __import__("pytest").raises(NotImplementedError, match="Phase 2"):
        p.list_models()
    with __import__("pytest").raises(NotImplementedError, match="Phase 2"):
        p.start("anything")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest desktop/tests/test_providers_protocol.py::test_paperclip_provider_is_phase2_stub -v`
Expected: `ModuleNotFoundError: No module named 'desktop.providers.paperclip'`.

- [ ] **Step 3: Implement the stub**

```python
# desktop/providers/paperclip.py
"""Paperclip provider — Phase 2 stub.

TODO(phase-2): Implement against Paperclip's HTTP API. Surface Paperclip-hired
agents matching role/skill filters as model options, and on start() return env
vars routing the upstream FastAPI request handler at Paperclip's chat endpoint
(or an OpenAI-compatible bridge if Paperclip exposes one).

Paperclip URL configured via Settings page once shipped.
"""

from __future__ import annotations

from desktop.providers import ProviderEnv


class PaperclipProvider:
    name: str = "paperclip"

    def is_available(self) -> bool:
        return False  # always unavailable until Phase 2 lands

    def list_models(self) -> list[str]:
        raise NotImplementedError(
            "Phase 2 — see TODO in desktop/providers/paperclip.py"
        )

    def start(self, model: str) -> ProviderEnv:
        raise NotImplementedError(
            "Phase 2 — see TODO in desktop/providers/paperclip.py"
        )

    def stop(self) -> None:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest desktop/tests/test_providers_protocol.py -v`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/providers/paperclip.py desktop/tests/test_providers_protocol.py
git commit -m "desktop: PaperclipProvider Phase-2 stub"
```

---

## Task 9: `desktop/providers/hermes.py` — Phase 2 stub

**Files:**
- Create: `desktop/providers/hermes.py`, append to `desktop/tests/test_providers_protocol.py`

- [ ] **Step 1: Write the failing test**

Append to `desktop/tests/test_providers_protocol.py`:

```python
# (append at end)
from desktop.providers.hermes import HermesProvider


def test_hermes_provider_is_phase2_stub():
    p = HermesProvider()
    assert p.name == "hermes"
    assert p.is_available() is False
    with __import__("pytest").raises(NotImplementedError, match="Phase 2"):
        p.list_models()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest desktop/tests/test_providers_protocol.py::test_hermes_provider_is_phase2_stub -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the stub**

```python
# desktop/providers/hermes.py
"""Hermes-agents provider — Phase 2 stub.

TODO(phase-2): Auto-download the canonical Hermes 3 Llama-3.1 8B GGUF into the
configured model directory and register it under the "Hermes Agents" label in
the picker. If the v2026.5.7 release is an agent runtime rather than just
weights, spawn that runtime as a separate provider and route via its
OpenAI-compatible bridge.

Reference: https://github.com/NousResearch/hermes-agent/releases/tag/v2026.5.7
"""

from __future__ import annotations

from desktop.providers import ProviderEnv


class HermesProvider:
    name: str = "hermes"

    def is_available(self) -> bool:
        return False

    def list_models(self) -> list[str]:
        raise NotImplementedError("Phase 2 — see TODO in desktop/providers/hermes.py")

    def start(self, model: str) -> ProviderEnv:
        raise NotImplementedError("Phase 2 — see TODO in desktop/providers/hermes.py")

    def stop(self) -> None:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest desktop/tests/test_providers_protocol.py -v`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/providers/hermes.py desktop/tests/test_providers_protocol.py
git commit -m "desktop: HermesProvider Phase-2 stub"
```

---

## Task 10: `desktop/launcher.py` — process supervisor

The supervisor: spawns SurrealDB → waits ready → spawns FastAPI uvicorn → waits ready → spawns worker → spawns Next.js → opens window. Tears everything down on quit.

**Files:**
- Create: `desktop/launcher.py`, `desktop/tests/test_launcher.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/tests/test_launcher.py
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desktop.config import Config
from desktop.launcher import Supervisor


def make_config(tmp_path: Path) -> Config:
    return Config(
        model_dir=tmp_path,
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password="A" * 24,
    )


@pytest.fixture
def cfg(tmp_path):
    return make_config(tmp_path)


def _alive_proc():
    p = MagicMock(spec=subprocess.Popen)
    p.poll.return_value = None
    return p


def test_supervisor_starts_all_children_in_order(cfg, tmp_path, monkeypatch):
    started: list[str] = []
    procs = {name: _alive_proc() for name in ("surreal", "api", "worker", "next")}

    def fake_popen(args, **kw):
        first = args[0] if isinstance(args, list) else args.split()[0]
        if "surreal" in first:
            started.append("surreal")
            return procs["surreal"]
        if "uvicorn" in (args[1] if len(args) > 1 else "") or "uvicorn" in first:
            started.append("api")
            return procs["api"]
        if "worker" in " ".join(args) if isinstance(args, list) else "worker" in args:
            started.append("worker")
            return procs["worker"]
        if "node" in first or "next" in " ".join(args):
            started.append("next")
            return procs["next"]
        raise AssertionError(f"unexpected popen: {args}")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: [40001, 40002, 40003]
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )
    sv.start_all()
    try:
        assert started == ["surreal", "api", "worker", "next"]
        assert sv.frontend_url.startswith("http://127.0.0.1:")
    finally:
        sv.stop_all()


def test_supervisor_stop_all_terminates_children(cfg, tmp_path, monkeypatch):
    procs = [_alive_proc() for _ in range(4)]
    seq = iter(procs)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: next(seq))
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: [40001, 40002, 40003]
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
    )
    sv.start_all()
    sv.stop_all()
    for p in procs:
        p.terminate.assert_called()


def test_supervisor_writes_session_env(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: _alive_proc())
    monkeypatch.setattr(
        "desktop.launcher.find_free_ports", lambda n: [40001, 40002, 40003]
    )
    monkeypatch.setattr("desktop.launcher._wait_tcp", lambda *a, **kw: None)
    monkeypatch.setattr("desktop.launcher._wait_http", lambda *a, **kw: None)

    sv = Supervisor(
        cfg=cfg,
        repo_root=tmp_path,
        bin_dir=tmp_path / "bin",
        surreal_arch="darwin-arm64",
        node_arch="darwin-arm64",
        extra_env={
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            "DEFAULT_MODEL": "llama3.1",
        },
    )
    sv.start_all()
    try:
        assert sv.session_env["OLLAMA_BASE_URL"] == "http://127.0.0.1:11434"
        assert sv.session_env["DEFAULT_MODEL"] == "llama3.1"
        assert sv.session_env["SURREAL_URL"].startswith("ws://127.0.0.1:")
        assert sv.session_env["SURREAL_USER"] == "root"
        assert sv.session_env["SURREAL_PASSWORD"] == "A" * 24
    finally:
        sv.stop_all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest desktop/tests/test_launcher.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement Supervisor**

```python
# desktop/launcher.py
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
import time
from pathlib import Path

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
    ) -> None:
        self.cfg = cfg
        self.repo_root = repo_root
        self.bin_dir = bin_dir
        self.surreal_arch = surreal_arch
        self.node_arch = node_arch
        self.extra_env = dict(extra_env or {})
        self._procs: list[subprocess.Popen] = []
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
        self._procs.clear()

    def _spawn(self, args: list[str], cwd: Path | None = None) -> subprocess.Popen:
        proc = subprocess.Popen(
            args,
            cwd=str(cwd) if cwd else None,
            env=self.session_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._procs.append(proc)
        return proc

    def _spawn_surreal(self, port: int) -> None:
        ext = ".exe" if self.surreal_arch.startswith("windows") else ""
        binary = self.bin_dir / f"surreal-{self.surreal_arch}{ext}"
        data_dir = (
            Path(os.environ.get("HOME", os.environ.get("USERPROFILE", ".")))
            / ".open-notebook-plus"
            / "surreal_data"
        )
        data_dir.mkdir(parents=True, exist_ok=True)
        self._spawn(
            [
                str(binary),
                "start",
                "--user",
                self.cfg.surreal_user,
                "--pass",
                self.cfg.surreal_password,
                "--bind",
                f"127.0.0.1:{port}",
                f"file://{data_dir}",
            ]
        )

    def _spawn_api(self, port: int) -> None:
        self._spawn(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "api.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=self.repo_root,
        )

    def _spawn_worker(self) -> None:
        # Upstream uses `surreal-commands` as the worker runtime; the worker
        # discovers commands via the same SURREAL_* env vars.
        self._spawn(
            [sys.executable, "-m", "surreal_commands.worker"],
            cwd=self.repo_root,
        )

    def _spawn_next(self, port: int) -> None:
        node_bin = (
            self.bin_dir
            / f"node-{self.node_arch}"
            / ("node.exe" if self.node_arch.startswith("windows") else "bin/node")
        )
        self._spawn(
            [str(node_bin), "start-server.js"],
            cwd=self.repo_root / "frontend",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest desktop/tests/test_launcher.py -v`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add desktop/launcher.py desktop/tests/test_launcher.py
git commit -m "desktop: Supervisor for Surreal/API/worker/Next children with session env"
```

---

## Task 11: `desktop/window.py` — PyWebView native window

**Files:**
- Create: `desktop/window.py`

(No tests — PyWebView isn't unit-testable; covered by smoke test in Task 18.)

- [ ] **Step 1: Write the window module**

```python
# desktop/window.py
"""PyWebView window wrapper. Opens a native window pointed at a URL and
calls a teardown callback on close."""

from __future__ import annotations

from typing import Callable

import webview


def open_window(
    url: str,
    on_close: Callable[[], None],
    title: str = "open-notebook-Plus",
    width: int = 1280,
    height: int = 800,
) -> None:
    """Blocking — returns when the user closes the window."""
    window = webview.create_window(title, url, width=width, height=height)
    window.events.closed += on_close
    webview.start()
```

- [ ] **Step 2: Sanity-import**

Run: `cd /Users/Antman/Desktop/OpenNotebook/open-notebook-Plus && pip install pywebview==5.4 && python -c "from desktop.window import open_window; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add desktop/window.py
git commit -m "desktop: PyWebView window wrapper"
```

---

## Task 12: Wire launcher entrypoint — `python -m desktop` boots the app

**Files:**
- Modify: `desktop/__init__.py` (add `__main__`-friendly factory)
- Create: `desktop/__main__.py`

- [ ] **Step 1: Implement `__main__.py`**

```python
# desktop/__main__.py
"""`python -m desktop` — boots config → wizard if needed → supervisor → window."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from desktop.config import default_config_path, load_or_create
from desktop.launcher import Supervisor
from desktop.providers.llamacpp import LlamaCppProvider
from desktop.providers.ollama import OllamaProvider
from desktop.window import open_window


def host_arch() -> str:
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "darwin-arm64" if machine in ("arm64", "aarch64") else "darwin-x86_64"
    if sys.platform == "win32":
        return "windows-x86_64"
    raise RuntimeError(f"unsupported platform {sys.platform}/{machine}")


def repo_root() -> Path:
    # When frozen by PyInstaller, sys._MEIPASS holds the bundle resource dir.
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def main() -> int:
    cfg_path = default_config_path()
    first_run = not cfg_path.exists()

    if first_run:
        from desktop.first_run.server import run_wizard_blocking

        run_wizard_blocking(cfg_path)

    cfg = load_or_create(cfg_path)
    arch = host_arch()
    bin_dir = repo_root() / "desktop" / "bin"

    extra_env: dict[str, str] = {}
    if cfg.provider == "ollama":
        ol = OllamaProvider()
        if ol.is_available():
            extra_env = ol.start(cfg.default_model or "")
    elif cfg.provider == "llamacpp":
        lc = LlamaCppProvider(model_dir=cfg.model_dir)
        if cfg.default_model:
            extra_env = lc.start(cfg.default_model)

    sv = Supervisor(
        cfg=cfg,
        repo_root=repo_root(),
        bin_dir=bin_dir,
        surreal_arch=arch,
        node_arch=arch,
        extra_env=extra_env,
    )
    sv.start_all()
    try:
        open_window(sv.frontend_url, on_close=sv.stop_all)
    finally:
        sv.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Sanity-import**

Run: `cd /Users/Antman/Desktop/OpenNotebook/open-notebook-Plus && python -c "import desktop.__main__; print('ok')"`
Expected: `ok` (no execution because `if __name__ == '__main__'` guard).

- [ ] **Step 3: Commit**

```bash
git add desktop/__main__.py
git commit -m "desktop: __main__ entrypoint wiring config → providers → supervisor → window"
```

---

## Task 13: First-run wizard — aiohttp server

Tiny aiohttp server serving 4 static screens; POSTs back to `/api/save` write the config and shut down.

**Files:**
- Create: `desktop/first_run/__init__.py`, `desktop/first_run/server.py`, `desktop/tests/test_first_run.py`

- [ ] **Step 1: Write the failing tests**

```python
# desktop/tests/test_first_run.py
import json
from pathlib import Path

import pytest
from aiohttp.test_utils import AioHTTPTestCase

from desktop.first_run.server import build_app


class WizardTestCase(AioHTTPTestCase):
    cfg_path: Path

    async def get_application(self):
        return build_app(self.cfg_path, on_done=lambda: None)

    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.cfg_path = Path(self._tmpdir) / "config.toml"
        super().setUp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)
        super().tearDown()

    async def test_get_index_returns_html(self):
        resp = await self.client.get("/")
        assert resp.status == 200
        assert "text/html" in resp.headers["Content-Type"]
        body = await resp.text()
        assert "open-notebook-Plus" in body

    async def test_post_save_writes_config(self):
        payload = {
            "model_dir": str(self.cfg_path.parent / "AI"),
            "provider": "llamacpp",
            "default_model": "x.gguf",
        }
        resp = await self.client.post(
            "/api/save",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 200
        assert self.cfg_path.exists()
        text = self.cfg_path.read_text()
        assert 'provider = "llamacpp"' in text
        assert 'default_model = "x.gguf"' in text

    async def test_post_save_rejects_invalid_provider(self):
        payload = {"model_dir": "/tmp", "provider": "bogus", "default_model": ""}
        resp = await self.client.post(
            "/api/save",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400


@pytest.mark.asyncio
async def test_build_app_returns_aiohttp_application(tmp_path):
    from aiohttp import web

    app = build_app(tmp_path / "config.toml", on_done=lambda: None)
    assert isinstance(app, web.Application)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest desktop/tests/test_first_run.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the wizard server**

```python
# desktop/first_run/__init__.py
```

```python
# desktop/first_run/server.py
"""First-run wizard: tiny aiohttp app serving 4 static screens.

Only used the very first time the app boots (no config.toml exists). Once the
user clicks Done, the wizard writes the config and signals completion.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Callable

from aiohttp import web

from desktop.config import Config

_VALID_PROVIDERS = {"ollama", "llamacpp", "none"}
STATIC_DIR = Path(__file__).parent / "static"


def build_app(config_path: Path, on_done: Callable[[], None]) -> web.Application:
    app = web.Application()

    async def index(_: web.Request) -> web.Response:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def save(req: web.Request) -> web.Response:
        body = await req.json()
        provider = body.get("provider", "none")
        if provider not in _VALID_PROVIDERS:
            return web.json_response({"error": "invalid provider"}, status=400)
        cfg = Config(
            model_dir=Path(body["model_dir"]),
            provider=provider,
            default_model=body.get("default_model", ""),
            surreal_user="root",
            surreal_password=secrets.token_urlsafe(24),
        )
        cfg.save(config_path)
        on_done()
        return web.json_response({"ok": True})

    app.router.add_get("/", index)
    app.router.add_post("/api/save", save)
    app.router.add_static("/static", STATIC_DIR)
    return app


def run_wizard_blocking(config_path: Path) -> None:
    """Open the wizard in PyWebView; return once the user clicks Done."""
    import asyncio
    import threading

    import webview

    done = threading.Event()
    runner_loop: asyncio.AbstractEventLoop | None = None
    runner: web.AppRunner | None = None
    site_port = 0

    def serve():
        nonlocal runner_loop, runner, site_port
        runner_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(runner_loop)
        app = build_app(config_path, on_done=done.set)
        runner = web.AppRunner(app)
        runner_loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, "127.0.0.1", 0)
        runner_loop.run_until_complete(site.start())
        site_port = site._server.sockets[0].getsockname()[1]
        runner_loop.run_forever()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    while site_port == 0:
        import time as _t

        _t.sleep(0.05)

    window = webview.create_window(
        "open-notebook-Plus — Setup",
        f"http://127.0.0.1:{site_port}/",
        width=720,
        height=540,
    )

    def _watch_done():
        import time as _t

        while not done.is_set():
            _t.sleep(0.2)
        window.destroy()

    threading.Thread(target=_watch_done, daemon=True).start()
    webview.start()

    if runner_loop is not None and runner is not None:
        runner_loop.call_soon_threadsafe(runner_loop.stop)
```

- [ ] **Step 4: Create placeholder static files (Task 14 fills them in)**

```bash
mkdir -p /Users/Antman/Desktop/OpenNotebook/open-notebook-Plus/desktop/first_run/static
```

```html
<!-- desktop/first_run/static/index.html -->
<!doctype html><html><body><h1>open-notebook-Plus</h1>
<p>Wizard placeholder — replaced in Task 14.</p></body></html>
```

- [ ] **Step 5: Configure pytest to find pytest-asyncio**

Append to `pyproject.toml` (root, near other tool config):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["desktop/tests", "tests"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest desktop/tests/test_first_run.py -v`
Expected: `4 passed`.

- [ ] **Step 7: Commit**

```bash
git add desktop/first_run/ pyproject.toml
git commit -m "desktop: first-run wizard aiohttp server with static-HTML screens"
```

---

## Task 14: Wizard HTML/CSS/JS — 4 screens

**Files:**
- Create: `desktop/first_run/static/index.html`, `style.css`, `wizard.js`

(No new tests; the server tests in Task 13 already cover save semantics.)

- [ ] **Step 1: Write `index.html`**

```html
<!-- desktop/first_run/static/index.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>open-notebook-Plus — Setup</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <main id="app">
    <section data-screen="welcome">
      <h1>open-notebook-Plus</h1>
      <p>Local-first AI notebooks. Let's get you set up — about 60 seconds.</p>
      <button data-next="dir">Continue</button>
    </section>

    <section data-screen="dir" hidden>
      <h2>Where should we look for models?</h2>
      <p>GGUF files in this directory show up in the model picker.</p>
      <input type="text" id="model_dir" />
      <p class="hint" id="model_dir_hint"></p>
      <button data-back="welcome">Back</button>
      <button data-next="model">Continue</button>
    </section>

    <section data-screen="model" hidden>
      <h2>Pick a starting model</h2>
      <ul id="model_choices">
        <li><label><input type="radio" name="choice" value="ollama" />
          Use Ollama (auto-detected models)</label></li>
        <li><label><input type="radio" name="choice" value="llamacpp" checked />
          Use llama.cpp with a local GGUF</label></li>
        <li><label><input type="radio" name="choice" value="none" />
          Skip — I'll pick later in Settings</label></li>
      </ul>
      <select id="default_model" hidden></select>
      <button data-back="dir">Back</button>
      <button data-next="done">Continue</button>
    </section>

    <section data-screen="done" hidden>
      <h2>You're set.</h2>
      <p>Saving config and starting open-notebook-Plus…</p>
      <p id="done_status"></p>
    </section>
  </main>
  <script src="/static/wizard.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `style.css`**

```css
/* desktop/first_run/static/style.css */
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       margin: 0; padding: 32px; background: #fafafa; color: #222; }
section { max-width: 540px; margin: 0 auto; }
h1, h2 { margin-top: 0; }
input[type=text] { width: 100%; padding: 8px 10px; font-size: 14px;
                   border: 1px solid #ccc; border-radius: 6px; }
button { padding: 10px 18px; font-size: 14px; border-radius: 6px;
         border: 1px solid #555; background: #222; color: #fff;
         cursor: pointer; margin-right: 8px; margin-top: 16px; }
button[data-back] { background: #fff; color: #222; }
ul { list-style: none; padding: 0; }
li label { display: block; padding: 10px; border: 1px solid #ddd;
           border-radius: 6px; margin-bottom: 8px; cursor: pointer; }
.hint { color: #888; font-size: 12px; margin-top: 4px; }
```

- [ ] **Step 3: Write `wizard.js`**

```javascript
// desktop/first_run/static/wizard.js
(() => {
  const screens = document.querySelectorAll('[data-screen]');
  const show = (name) => screens.forEach(s =>
    s.hidden = s.dataset.screen !== name);

  // Pre-fill model dir with platform default (server doesn't know HOME at render time)
  const modelDirInput = document.getElementById('model_dir');
  modelDirInput.value = navigator.platform.toLowerCase().includes('win')
    ? '%USERPROFILE%\\Desktop\\AI_Models'
    : '~/Desktop/AI_Models';

  document.querySelectorAll('button[data-next], button[data-back]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const target = btn.dataset.next || btn.dataset.back;
      if (target === 'done') {
        const choice = document.querySelector('input[name=choice]:checked').value;
        const payload = {
          model_dir: modelDirInput.value
            .replace(/^~/, document.body.dataset.home || '')
            .replace(/^%USERPROFILE%/, document.body.dataset.userprofile || ''),
          provider: choice,
          default_model: document.getElementById('default_model').value || ''
        };
        show('done');
        document.getElementById('done_status').textContent = 'Saving…';
        const r = await fetch('/api/save', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        document.getElementById('done_status').textContent = r.ok
          ? 'Saved. You can close this window.'
          : 'Error saving config; check logs.';
      } else {
        show(target);
      }
    });
  });

  show('welcome');
})();
```

- [ ] **Step 4: Sanity-load locally**

Run:
```bash
cd /Users/Antman/Desktop/OpenNotebook/open-notebook-Plus
python -c "
from desktop.first_run.server import build_app
from aiohttp import web
import asyncio, tempfile, pathlib
async def main():
    app = build_app(pathlib.Path(tempfile.mkstemp(suffix='.toml')[1]), on_done=lambda: print('done'))
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 8765); await site.start()
    print('http://127.0.0.1:8765')
    await asyncio.sleep(2)
    await runner.cleanup()
asyncio.run(main())
"
```
Expected: prints URL; if you hit it in a browser within 2 seconds you see the welcome screen.

- [ ] **Step 5: Commit**

```bash
git add desktop/first_run/static/
git commit -m "desktop: 4-screen first-run wizard UI"
```

---

## Task 15: `desktop/build/pyinstaller.spec`

**Files:**
- Create: `desktop/build/pyinstaller.spec`

(No tests — covered by build-and-launch smoke in Task 18.)

- [ ] **Step 1: Write the spec**

```python
# desktop/build/pyinstaller.spec
# Run with: pyinstaller desktop/build/pyinstaller.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]  # SPECPATH = desktop/build
PROJECT_ROOT = ROOT.parent

is_mac = sys.platform == "darwin"
is_win = sys.platform == "win32"

# arch suffix used by fetch_runtimes.py
import platform as _pl

_machine = _pl.machine().lower()
if is_mac:
    arch = "darwin-arm64" if _machine in ("arm64", "aarch64") else "darwin-x86_64"
elif is_win:
    arch = "windows-x86_64"
else:
    raise RuntimeError("unsupported platform")

bin_dir = ROOT / "bin"
node_dir = bin_dir / f"node-{arch}"
surreal_bin = bin_dir / (f"surreal-{arch}.exe" if is_win else f"surreal-{arch}")
frontend_dir = PROJECT_ROOT / "frontend"

datas = [
    # Upstream Python source (FastAPI + worker + open_notebook package)
    (str(PROJECT_ROOT / "api"), "api"),
    (str(PROJECT_ROOT / "open_notebook"), "open_notebook"),
    (str(PROJECT_ROOT / "commands"), "commands"),
    (str(PROJECT_ROOT / "prompts"), "prompts"),
    # Frontend production build
    (str(frontend_dir / ".next"), "frontend/.next"),
    (str(frontend_dir / "public"), "frontend/public"),
    (str(frontend_dir / "package.json"), "frontend"),
    (str(frontend_dir / "start-server.js"), "frontend"),
    (str(frontend_dir / "next.config.ts"), "frontend"),
    (str(frontend_dir / "node_modules"), "frontend/node_modules"),
    # Wizard static assets
    (str(ROOT / "first_run" / "static"), "desktop/first_run/static"),
    # Bundled binaries
    (str(surreal_bin), "desktop/bin"),
    (str(node_dir), f"desktop/bin/node-{arch}"),
]

hiddenimports = [
    "uvicorn",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.lifespan.on",
    "uvicorn.loops.auto",
    "uvicorn.protocols.websockets.auto",
    "surreal_commands.worker",
    "llama_cpp.server",
    "langchain_openai",
    "langchain_anthropic",
    "langchain_ollama",
    "langchain_google_genai",
    "langchain_groq",
    "langchain_mistralai",
    "langchain_deepseek",
]

a = Analysis(
    [str(ROOT.parent / "desktop" / "__main__.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "streamlit"
    ],  # upstream lint config mentions Streamlit; runtime doesn't need it
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="open-notebook-Plus",
    console=False,
    icon=str(ROOT / "resources" / ("icon.icns" if is_mac else "icon.ico")),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="open-notebook-Plus",
)

if is_mac:
    app = BUNDLE(
        coll,
        name="open-notebook-Plus.app",
        icon=str(ROOT / "resources" / "icon.icns"),
        bundle_identifier="com.antman1526.open-notebook-plus",
        info_plist={
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
        },
    )
```

- [ ] **Step 2: Add placeholder icons (real ones can come later)**

```bash
mkdir -p desktop/resources
# Use any 512x512 PNG as a placeholder for now; real icons via Task 22.
python - <<'PY'
import struct, zlib
from pathlib import Path
def png_solid(rgba, w=512, h=512):
    sig = b'\x89PNG\r\n\x1a\n'
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    raw = b''
    for _ in range(h):
        raw += b'\x00' + bytes(rgba) * w
    idat = chunk(b'IDAT', zlib.compress(raw))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend
Path('desktop/resources/icon.png').write_bytes(png_solid([24, 24, 28, 255]))
PY
# Mac: convert PNG → .icns via sips (macOS-only, fine for local dev).
mkdir -p desktop/resources/icon.iconset
sips -z 512 512 desktop/resources/icon.png --out desktop/resources/icon.iconset/icon_512x512.png
iconutil -c icns desktop/resources/icon.iconset -o desktop/resources/icon.icns
rm -rf desktop/resources/icon.iconset
# Windows: a simple .ico via Pillow during the win build. For now stub it.
cp desktop/resources/icon.png desktop/resources/icon.ico
```

- [ ] **Step 3: Commit**

```bash
git add desktop/build/pyinstaller.spec desktop/resources/
git commit -m "desktop: PyInstaller spec + placeholder icons"
```

---

## Task 16: Mac post-build script — `.app` → `.dmg`

**Files:**
- Create: `desktop/build/post_build_mac.sh`

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# desktop/build/post_build_mac.sh — wrap dist/open-notebook-Plus.app into a .dmg
set -euo pipefail

APP_NAME="open-notebook-Plus"
APP_PATH="dist/${APP_NAME}.app"
DMG_PATH="dist/${APP_NAME}-mac-$(uname -m).dmg"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "ERROR: ${APP_PATH} not found. Run pyinstaller first." >&2
  exit 1
fi

rm -f "${DMG_PATH}"
hdiutil create -volname "${APP_NAME}" \
               -srcfolder "${APP_PATH}" \
               -ov -format UDZO "${DMG_PATH}"
echo "Built ${DMG_PATH}"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x desktop/build/post_build_mac.sh
```

- [ ] **Step 3: Commit**

```bash
git add desktop/build/post_build_mac.sh
git commit -m "desktop: post_build_mac.sh — wrap .app into .dmg"
```

---

## Task 17: Windows post-build script — folder → `.zip`

**Files:**
- Create: `desktop/build/post_build_windows.ps1`

- [ ] **Step 1: Write the script**

```powershell
# desktop/build/post_build_windows.ps1 — wrap dist/open-notebook-Plus into a .zip
$ErrorActionPreference = "Stop"
$Name = "open-notebook-Plus"
$Src = "dist\$Name"
$Dest = "dist\$Name-windows-x64.zip"

if (-not (Test-Path $Src)) {
  Write-Error "$Src not found. Run pyinstaller first."
  exit 1
}

if (Test-Path $Dest) { Remove-Item $Dest }
Compress-Archive -Path "$Src\*" -DestinationPath $Dest
Write-Host "Built $Dest"
```

- [ ] **Step 2: Commit**

```bash
git add desktop/build/post_build_windows.ps1
git commit -m "desktop: post_build_windows.ps1 — zip the dist folder"
```

---

## Task 18: Local Mac smoke test (manual)

**Files:**
- (None — this is a manual verification step.)

- [ ] **Step 1: Run the local Mac build**

Run:
```bash
cd /Users/Antman/Desktop/OpenNotebook/open-notebook-Plus
pip install -r desktop/requirements.txt
pip install -e .
cd frontend && npm ci && npm run build && cd ..
python desktop/build/fetch_runtimes.py
pyinstaller desktop/build/pyinstaller.spec --noconfirm
desktop/build/post_build_mac.sh
```
Expected: `dist/open-notebook-Plus.app` exists; `dist/open-notebook-Plus-mac-arm64.dmg` exists.

- [ ] **Step 2: Launch the .app**

Run: `open dist/open-notebook-Plus.app`
Expected (first launch with no `~/.open-notebook-plus/config.toml`):
- Wizard window opens.
- After clicking through to Done, main window opens within ~10 s.
- The main window shows the open-notebook UI.
- Quitting the window leaves no orphan processes (`pgrep -f surreal && echo orphan || echo clean`).

- [ ] **Step 3: Verify model picker sees the AI_Models GGUFs**

In the main UI, navigate to Settings → Models. Expected: the 19 GGUFs from `/Users/Antman/Desktop/AI_Models/GGUF/` are listed.

- [ ] **Step 4: If anything fails**

Capture `stdout/stderr` of the launched app:
```
open dist/open-notebook-Plus.app --stdout /tmp/onp.out --stderr /tmp/onp.err
tail -200 /tmp/onp.err
```
Diagnose, fix in the relevant earlier task, rerun.

- [ ] **Step 5: Commit any fixes that emerged**

```bash
git add -A
git commit -m "desktop: smoke-test fixes from local Mac build"
```

---

## Task 19: GitHub Actions — `.github/workflows/build-desktop.yml`

**Files:**
- Create: `.github/workflows/build-desktop.yml`

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/build-desktop.yml
name: build-desktop

on:
  push:
    branches: [main, desktop-app]
    tags: ['v*']

jobs:
  build-mac-arm64:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: pip install -r desktop/requirements.txt
      - run: pip install -e .
      - run: cd frontend && npm ci && npm run build
      - run: python desktop/build/fetch_runtimes.py
      - run: pyinstaller desktop/build/pyinstaller.spec --noconfirm
      - run: bash desktop/build/post_build_mac.sh
      - uses: actions/upload-artifact@v4
        with:
          name: open-notebook-Plus-mac-arm64
          path: dist/open-notebook-Plus-mac-arm64.dmg

  build-mac-x86_64:
    runs-on: macos-13
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: pip install -r desktop/requirements.txt
      - run: pip install -e .
      - run: cd frontend && npm ci && npm run build
      - run: python desktop/build/fetch_runtimes.py
      - run: pyinstaller desktop/build/pyinstaller.spec --noconfirm
      - run: bash desktop/build/post_build_mac.sh
      - uses: actions/upload-artifact@v4
        with:
          name: open-notebook-Plus-mac-x86_64
          path: dist/open-notebook-Plus-mac-x86_64.dmg

  build-windows-x64:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: pip install -r desktop/requirements.txt
      - run: pip install -e .
      - run: cd frontend; npm ci; npm run build
      - run: python desktop/build/fetch_runtimes.py
      - run: pyinstaller desktop/build/pyinstaller.spec --noconfirm
      - run: pwsh desktop/build/post_build_windows.ps1
      - uses: actions/upload-artifact@v4
        with:
          name: open-notebook-Plus-windows-x64
          path: dist/open-notebook-Plus-windows-x64.zip

  release:
    needs: [build-mac-arm64, build-mac-x86_64, build-windows-x64]
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with: { path: dist }
      - uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/open-notebook-Plus-mac-arm64/*.dmg
            dist/open-notebook-Plus-mac-x86_64/*.dmg
            dist/open-notebook-Plus-windows-x64/*.zip
```

- [ ] **Step 2: Push the branch and watch the first run**

```bash
git add .github/workflows/build-desktop.yml
git commit -m "ci: GitHub Actions desktop build for mac arm64 + mac x64 + windows x64"
git push -u origin desktop-app
gh run watch
```
Expected: all 3 build jobs succeed, artifacts available in the run page.

- [ ] **Step 3: Diagnose and fix any CI-only failures**

Common gotchas:
- macOS runners may not have `iconutil`/`sips` if icons differ → fall back to plain `.icns` checked into `desktop/resources/`.
- Windows `pip install` of `llama-cpp-python` needs MSVC build tools — runner image already has them.
- Frontend `npm run build` may need a `.env` with `NEXT_PUBLIC_API_BASE` placeholder; if so add to the YAML.

Iterate until green; commit fixes.

---

## Task 20: Top-level README rewrite

**Files:**
- Modify: `README.md` (full rewrite — backup the original first)

- [ ] **Step 1: Save the upstream README as `README.upstream.md`**

```bash
cp README.md README.upstream.md
git add README.upstream.md
```

- [ ] **Step 2: Write the new top-level README**

```markdown
# open-notebook-Plus

A desktop-app fork of [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook)
focused on **local-first AI notebooks**.

## What's different from upstream

- Native desktop app: Mac `.dmg`, Windows `.zip` — no Docker, no terminal.
- Bundles SurrealDB and a portable Node.js runtime; no separate installs.
- **Local-model-first:** Ollama auto-detect + llama.cpp via a local GGUF directory.
- Cloud APIs are optional and off by default.
- Phase 2 (placeholder): Paperclip provider + Hermes-agents support.

## Install

- **Mac:** Download the `.dmg` from
  [Releases](https://github.com/Antman1526/open-notebook-Plus/releases), drag
  the app to **Applications**, then **right-click → Open** the first time
  (unsigned build; macOS Gatekeeper).
- **Windows:** Download the `.zip` from Releases, extract anywhere, run
  `open-notebook-Plus.exe`. SmartScreen will warn — click **More info →
  Run anyway** (unsigned build).

## First run

1. Pick a model directory (default: `~/Desktop/AI_Models` on Mac,
   `%USERPROFILE%\Desktop\AI_Models` on Windows).
2. Pick a starting model: download Llama 3.1 8B, use installed Ollama, or skip.
3. Done — the main UI opens.

## Adding more models

- Drop any `.gguf` file into your model directory (subdirectories are scanned
  too); it appears in the picker on next launch.
- `ollama pull <name>` — Ollama-installed models show up under the Ollama
  section in the picker.

## Building from source

```
git clone https://github.com/Antman1526/open-notebook-Plus
cd open-notebook-Plus
pip install -r desktop/requirements.txt
pip install -e .
cd frontend && npm ci && npm run build && cd ..
python desktop/build/fetch_runtimes.py
pyinstaller desktop/build/pyinstaller.spec --noconfirm
# Mac:    desktop/build/post_build_mac.sh
# Windows: pwsh desktop/build/post_build_windows.ps1
```

CI: tag `vX.Y.Z` → GitHub Actions builds `.dmg` (arm64 + x86_64) and `.exe`
zip and attaches them to a Release.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  open-notebook-Plus.app / .exe                       │
│                                                      │
│  PyWebView native window (loads frontend URL)        │
│                       │                              │
│  launcher.py supervisor                              │
│   ├─ SurrealDB (bundled binary)                      │
│   ├─ FastAPI uvicorn  (api/)                         │
│   ├─ open-notebook worker (surreal-commands)         │
│   ├─ Next.js frontend (bundled portable Node)        │
│   └─ model backend (Ollama discover OR llama.cpp)    │
│                                                      │
│  Bundled: Python 3.12 · Node.js 20 LTS · SurrealDB v2│
│  Models live OUTSIDE the bundle, in your model dir.  │
└──────────────────────────────────────────────────────┘
```

Full design and implementation plan:
- [docs/superpowers/specs/2026-05-09-open-notebook-plus-desktop-design.md](docs/superpowers/specs/2026-05-09-open-notebook-plus-desktop-design.md)
- [docs/superpowers/plans/2026-05-09-open-notebook-plus-desktop.md](docs/superpowers/plans/2026-05-09-open-notebook-plus-desktop.md)

## Credits

Forked from [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook) (MIT).
Upstream files remain unmodified; all wrapper code lives under `desktop/`.
Upstream README preserved at [README.upstream.md](README.upstream.md).
```

- [ ] **Step 3: Commit**

```bash
git add README.md README.upstream.md
git commit -m "docs: rewrite top-level README for the open-notebook-Plus fork"
```

---

## Task 21: Final end-to-end smoke test (manual)

**Files:**
- (None — verification only.)

- [ ] **Step 1: Confirm CI is green on the latest commit**

Run: `gh run list --branch desktop-app --limit 3`
Expected: most recent run shows `success` for all three build jobs.

- [ ] **Step 2: Download the Mac arm64 artifact and run it from a clean state**

```bash
rm -rf ~/.open-notebook-plus
gh run download --pattern 'open-notebook-Plus-mac-arm64' --dir /tmp/onp-test
hdiutil attach /tmp/onp-test/open-notebook-Plus-mac-arm64.dmg
cp -R "/Volumes/open-notebook-Plus/open-notebook-Plus.app" /tmp/
hdiutil detach "/Volumes/open-notebook-Plus"
open /tmp/open-notebook-Plus.app
```
Expected: wizard appears (config.toml didn't exist), then main UI loads, then chat works against an Ollama or llama.cpp model.

- [ ] **Step 3: Tag a v0.1.0 release**

```bash
git tag v0.1.0
git push origin v0.1.0
gh run watch
```
Expected: release workflow attaches all 3 artifacts to a new Release at
https://github.com/Antman1526/open-notebook-Plus/releases/tag/v0.1.0.

- [ ] **Step 4: Test the released `.dmg` from a fresh download**

Download from the Release page, run, confirm wizard → main UI → chat reply
all work end-to-end. **This is the definition-of-done check from the spec.**

---

## Self-review pass

I checked the plan against the spec section by section:

| Spec section | Covered by |
|---|---|
| Goals 1-5 | Tasks 1-21 collectively |
| Architecture (4-process supervisor + bundled Node + Surreal) | Tasks 4, 10, 12 |
| Repo structure (`desktop/` tree) | Tasks 1-9, 11, 13-17 |
| Local model handling (Ollama → llama.cpp → cloud) | Tasks 5-7, 12 |
| First-run flow (4 screens, aiohttp) | Tasks 13, 14 |
| Build pipeline (PyInstaller + 3 GH Actions jobs) | Tasks 4, 15-17, 19 |
| Phase 2 stubs (Paperclip + Hermes) | Tasks 8, 9 |
| README content | Tasks 1 (desktop/README.md), 20 (top-level) |
| Open question 1 (Streamlit lint refs) | Spec excludes `streamlit` in PyInstaller `excludes` (Task 15) |
| Open question 4 (Next.js port) | Task 10 sets `PORT` env var (Next.js convention) |
| Definition of done | Task 21, all 7 checklist items |

No placeholder text. No undefined types/methods cross-referenced. Provider method
names (`is_available`, `list_models`, `start`, `stop`) consistent across Tasks 5–9
and Task 12.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-09-open-notebook-plus-desktop.md`. Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

**Which approach?**

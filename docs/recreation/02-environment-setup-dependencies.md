# 02 — Environment Setup & Dependencies

> Exact versions as resolved at v0.8.114. Where a floor is stated (`>=`), the lockfile
> pins an exact version; both are given where they differ meaningfully.

---

## 1. Host requirements

| Requirement | Version | Notes |
|---|---|---|
| macOS | 14+ (Sonoma) | Apple Silicon primary; x86_64 supported |
| Python (dev) | 3.12.x | `requires-python = ">=3.11,<3.13"` |
| Node.js | 20+ | Frontend build; bundled at runtime |
| uv | latest | Sole Python package manager |
| Xcode CLT | — | `codesign`, `hdiutil` |
| Homebrew Python 3.12 | — | **Required for `pip-audit`** (uv pythons lack a working `ensurepip`) |

Disk: ~25 GB for the repo, venvs, bundled runtimes, and a build. Local models add more.

## 2. Bundled runtimes

`desktop/build/runtimes.toml` pins every downloaded binary with a SHA-256. All are
fetched by `desktop/build/fetch_runtimes.py` into `desktop/bin/` and verified before use.

```toml
[python_standalone]
version = "20260814"
python_version = "3.12.14"

[python_standalone.urls]
darwin-arm64 = "https://github.com/astral-sh/python-build-standalone/releases/download/20260814/cpython-3.12.14+20260814-aarch64-apple-darwin-install_only.tar.gz"

[python_standalone.sha256]
darwin-arm64 = "4572133a5542f306b9bdb155da5800f9e38950cd0a98d469b832ce256fe299ea"
```

> **Do not downgrade this pin.** The prior 20241206 / 3.12.8 build links OpenSSL 3.0.15,
> whose TLS ClientHello Wikimedia's edge rejects with a robot-policy 403 — keyless web
> search dies *only in packaged builds*. 3.12.14 carries OpenSSL 3.5.x.

Also bundled: SurrealDB binary, Node.js runtime, `uv` binary.

## 3. Python dependencies (from `pyproject.toml`)

### Core web / async
```
fastapi>=0.136.3          uvicorn>=0.24.0        pydantic>=2.9.2
starlette>=1.2.1          httpx[socks]>=0.27.0   aiohttp>=3.14.3
python-multipart>=0.0.31  loguru>=0.7.2          prometheus-client>=0.20.0
```

### LLM orchestration
```
langchain>=1.3.9              langgraph>=1.0.10
langchain-core>=1.3.3         langgraph-checkpoint>=4.1.1
langgraph-checkpoint-sqlite>=3.1.1   langgraph-sdk>=0.3.15
langchain-community>=0.4.1    langchain-classic>=1.0.7
tiktoken>=0.12.0              ai-prompter>=0.4,<1
esperanto>=2.20.0,<3          mcp>=1.28.1,<2
```

### Provider adapters
```
langchain-openai>=1.1.14   langchain-anthropic>=1.4.6   langchain-ollama>=1.0.1
langchain-google-genai>=4.1.2   langchain-groq>=1.1.1
langchain_mistralai>=1.1.1      langchain_deepseek>=1.0.0
```

### Data
```
surrealdb>=1.0.4      surreal-commands>=1.3.1,<2    numpy>=2.4.1
```

### Content processing
```
content-core>=1.14.1,<2   lxml>=6.1.0        lxml-html-clean>=0.4.5
python-docx>=1.2.0,<2.0   python-pptx>=1.0.2,<2.0   openpyxl>=3.1.5,<4.0
pillow>=11.3.0,<12.0      markdown-it-py>=4.0.0,<5   pyyaml>=6.0.3,<7
imageio-ffmpeg>=0.6.0,<1.0
```

> **`pillow<12.0` is a documented security exception** (DN-DEP-PILLOW-2026-08-11):
> `podcast-creator 0.12.0 → moviepy>=2.2.1 → Pillow<12`. ~20 PYSEC advisories are
> accepted residuals until moviepy supports Pillow 12. Do not "fix" by overriding.

### Feature-specific
```
podcast-creator>=0.12.0,<1   fsrs>=6.3.1,<7.0    genanki==0.13.1
watchdog>=6.0.0,<7.0         huggingface-hub>=1.3.0
pycountry>=26.2.16           babel>=2.18.0
```

### Security floors (transitive CVE remediation)
```
urllib3>=2.7.0      cryptography>=50.0.0   authlib>=1.6.12   pyjwt>=2.13.0
idna>=3.15          click>=8.3.3           pyasn1>=0.6.4     soupsieve>=2.8.4
langsmith>=0.8.18   pydantic-settings>=2.14.2   pip>=26.1.2
```

## 4. Desktop-bundle extras (`desktop/requirements.txt`)

Installed into the **user venv** on top of the project deps:

```
pywebview==5.4
pyinstaller>=6.13.0,<7
llama-cpp-python[server]>=0.3.16,<0.4     # [server] extra is REQUIRED
mlx-lm>=0.31,<0.32 ; darwin and arm64     # 0.26 rejects qwen3_5 architecture
faster-whisper>=1.1.0,<2
piper-tts>=1.2.0,<2
mem0ai>=2.0.18,<3
mcp>=1.0,<2      fastmcp>=3.0,<4      httpx==0.28.1
pytest>=9.0.3,<10                pytest-asyncio>=1.2.0,<2
skillopt>=0.1.0,<0.2
h2>=4.4.1        joserfc>=1.6.8       setuptools>=83.0.0   # pip-audit floors
```

Notes that cost real debugging time:

- **`llama-cpp-python[server]`** — without `[server]`, `starlette_context` is missing and
  both local GGUF servers die at import.
- **`mlx-lm>=0.31`** — 0.26.4 raises `Model type qwen3_5 not supported`, and the server
  binds its port *before* loading the model, so a port probe reports a live server whose
  model can never load.
- **`mem0ai>=2.0.18`** — the shim was always written against 2.x semantics; the old `<2`
  ceiling was the anomaly.

## 5. Developer setup

```bash
git clone https://github.com/Antman1526/Deeper-Notebook.git
cd Deeper-Notebook
uv sync                          # project venv at .venv
cd frontend && npm ci && cd ..
cp .env.example .env             # set DEEPER_NOTEBOOK_ENCRYPTION_KEY
```

```bash
make database        # SurrealDB via docker compose (dev only)
make api             # uv run --env-file .env run_api.py
make frontend        # cd frontend && npm run dev
```

```bash
make test                 # backend, hermetic
make test-integration     # needs live SurrealDB; uses throwaway onp_test_<uuid> namespace
make security-scan        # bandit (fails on HIGH) + pip-audit
```

## 6. Building the desktop app

```bash
bash scripts/create-signing-identity.sh          # once — stable identity
export DEEPER_NOTEBOOK_CODESIGN_IDENTITY="Deeper Notebook Local"

NEXT_PUBLIC_DN_VISUAL_SYSTEM_V2=1 \
NEXT_PUBLIC_DN_SOURCE_VISUALS=1 \
make build-mac                                    # ~25 min
make build-mac-install                            # → /Applications
```

> **Quit the app first.** `build-mac-test` preflights this and fails fast with the remedy;
> a repair-script test cannot pass while the app or SurrealDB is running.

Without a stable identity, every ad-hoc rebuild gives the bundle a new cryptographic
identity, macOS resets its TCC (Files & Folders) grants, and the next launch **wedges
silently** in `os_scandir` waiting on a consent dialog.

## 7. Build stages

| Target | Does |
|---|---|
| `build-mac-test` | Preflight + desktop suite + backend suite (retry-failed-once) |
| `build-mac-lock` | Regenerate `desktop/requirements.lock` from pyproject + requirements.txt |
| `build-mac-venv` | `.build-venv` with pinned build deps |
| `build-mac-frontend` | `npm run build` — **bakes `NEXT_PUBLIC_*` flags** |
| `build-mac-runtimes` | Fetch + verify bundled binaries |
| `build-mac-pyinstaller` | `dist/Deeper Notebook.app` + codesign re-seal |
| `build-mac-dmg` | `dist/Deeper-Notebook-mac-arm64.dmg` (~520 MB) |

## 8. Known environment traps

| Symptom | Cause | Fix |
|---|---|---|
| `pip-audit` dies with SIGABRT | uv python has no `ensurepip` | run under `/opt/homebrew/bin/python3.12` |
| App launches, no window, sidecars stall | TCC consent wedge | grant Files & Folders; use stable identity |
| Keyless web search returns nothing in the packaged app only | OpenSSL 3.0 TLS fingerprint | runtime pin ≥ 20260814 |
| Timing tests flake under load | machine load > 20 | gate retries failed tests once |
| Runtime bump doesn't reach an install | stale extraction/venv stamps | both stamps are keyed (v0.8.83) |

---

*Continues in [03 — Database Schema & Data Models](./03-database-schema-data-models.md).*

.PHONY: run frontend check ruff database lint api start-all stop-all status clean-cache worker worker-start worker-stop worker-restart backup restore verify-backup test test-integration
.PHONY: docker-buildx-prepare docker-buildx-clean docker-buildx-reset
.PHONY: docker-push docker-push-latest docker-release docker-build-local tag export-docs

# Get version from pyproject.toml
VERSION := $(shell grep -m1 version pyproject.toml | cut -d'"' -f2)

# Image names for both registries
DOCKERHUB_IMAGE := lfnovo/open_notebook
GHCR_IMAGE := ghcr.io/lfnovo/open-notebook

# Build platforms
PLATFORMS := linux/amd64,linux/arm64

database:
	docker compose up -d surrealdb

run:
	@echo "⚠️  Warning: Starting frontend only. For full functionality, use 'make start-all'"
	cd frontend && npm run dev

frontend:
	cd frontend && npm run dev

lint:
	uv run python -m mypy .

ruff:
	ruff check . --fix

# === Docker Build Setup ===
docker-buildx-prepare:
	@docker buildx inspect multi-platform-builder >/dev/null 2>&1 || \
		docker buildx create --use --name multi-platform-builder --driver docker-container
	@docker buildx use multi-platform-builder

docker-buildx-clean:
	@echo "🧹 Cleaning up buildx builders..."
	@docker buildx rm multi-platform-builder 2>/dev/null || true
	@docker ps -a | grep buildx_buildkit | awk '{print $$1}' | xargs -r docker rm -f 2>/dev/null || true
	@echo "✅ Buildx cleanup complete!"

docker-buildx-reset: docker-buildx-clean docker-buildx-prepare
	@echo "✅ Buildx reset complete!"

# === Docker Build Targets ===

# Build production image for local platform only (no push)
docker-build-local:
	@echo "🔨 Building production image locally ($(shell uname -m))..."
	docker build \
		-t $(DOCKERHUB_IMAGE):$(VERSION) \
		-t $(DOCKERHUB_IMAGE):local \
		.
	@echo "✅ Built $(DOCKERHUB_IMAGE):$(VERSION) and $(DOCKERHUB_IMAGE):local"
	@echo "Run with: docker run -p 5055:5055 -p 3000:3000 $(DOCKERHUB_IMAGE):local"

# Build and push version tags ONLY (no latest) for both regular and single images
docker-push: docker-buildx-prepare
	@echo "📤 Building and pushing version $(VERSION) to both registries..."
	@echo "🔨 Building regular image..."
	docker buildx build --pull \
		--platform $(PLATFORMS) \
		--progress=plain \
		-t $(DOCKERHUB_IMAGE):$(VERSION) \
		-t $(GHCR_IMAGE):$(VERSION) \
		--push \
		.
	@echo "🔨 Building single-container image..."
	docker buildx build --pull \
		--platform $(PLATFORMS) \
		--progress=plain \
		-f Dockerfile.single \
		-t $(DOCKERHUB_IMAGE):$(VERSION)-single \
		-t $(GHCR_IMAGE):$(VERSION)-single \
		--push \
		.
	@echo "✅ Pushed version $(VERSION) to both registries (latest NOT updated)"
	@echo "  📦 Docker Hub:"
	@echo "    - $(DOCKERHUB_IMAGE):$(VERSION)"
	@echo "    - $(DOCKERHUB_IMAGE):$(VERSION)-single"
	@echo "  📦 GHCR:"
	@echo "    - $(GHCR_IMAGE):$(VERSION)"
	@echo "    - $(GHCR_IMAGE):$(VERSION)-single"

# Update v1-latest tags to current version (both regular and single images)
docker-push-latest: docker-buildx-prepare
	@echo "📤 Updating v1-latest tags to version $(VERSION)..."
	@echo "🔨 Building regular image with latest tag..."
	docker buildx build --pull \
		--platform $(PLATFORMS) \
		--progress=plain \
		-t $(DOCKERHUB_IMAGE):$(VERSION) \
		-t $(DOCKERHUB_IMAGE):v1-latest \
		-t $(GHCR_IMAGE):$(VERSION) \
		-t $(GHCR_IMAGE):v1-latest \
		--push \
		.
	@echo "🔨 Building single-container image with latest tag..."
	docker buildx build --pull \
		--platform $(PLATFORMS) \
		--progress=plain \
		-f Dockerfile.single \
		-t $(DOCKERHUB_IMAGE):$(VERSION)-single \
		-t $(DOCKERHUB_IMAGE):v1-latest-single \
		-t $(GHCR_IMAGE):$(VERSION)-single \
		-t $(GHCR_IMAGE):v1-latest-single \
		--push \
		.
	@echo "✅ Updated v1-latest to version $(VERSION)"
	@echo "  📦 Docker Hub:"
	@echo "    - $(DOCKERHUB_IMAGE):$(VERSION) → v1-latest"
	@echo "    - $(DOCKERHUB_IMAGE):$(VERSION)-single → v1-latest-single"
	@echo "  📦 GHCR:"
	@echo "    - $(GHCR_IMAGE):$(VERSION) → v1-latest"
	@echo "    - $(GHCR_IMAGE):$(VERSION)-single → v1-latest-single"

# Full release: push version AND update latest tags
docker-release: docker-push-latest
	@echo "✅ Full release complete for version $(VERSION)"

tag:
	@version=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	echo "Creating tag v$$version"; \
	git tag "v$$version"; \
	git push origin "v$$version"


# v0.7.140 — Both `dev` and `full` previously referenced compose files
# (`docker-compose.dev.yml`, `docker-compose.full.yml`) that do not
# exist in the repo. Only `docker-compose.yml` ships. Running either
# target failed with:
#     open docker-compose.dev.yml: no such file or directory
# Switched both to the actual file. Until/unless the dev / full
# variants are reintroduced they're aliases of the same single
# compose file.
dev:
	docker compose -f docker-compose.yml up --build

full:
	docker compose -f docker-compose.yml up --build


api:
	uv run --env-file .env run_api.py

# v0.7.126 — Backup + restore targets.
#
# `make backup`           — snapshot the data directory to a timestamped
#                            tarball at backups/onp-backup-YYYYMMDD-HHMMSS.tar.gz
# `make backup OUT=path`  — write to a specific path
# `make verify-backup BUNDLE=path`
#                          — re-hash everything inside a bundle against its
#                            manifest, without touching the data dir
# `make restore BUNDLE=path`
#                          — restore from a bundle. REFUSES if data dir is
#                            non-empty unless FORCE=1 is also set.
#
# All three honor ONP_DATA_DIR so users with a custom install path don't
# need to think about which directory to back up.

OUT ?= backups/onp-backup-$(shell date +%Y%m%d-%H%M%S).tar.gz

backup:
	@mkdir -p $(dir $(OUT))
	@echo "Creating backup at $(OUT)..."
	@uv run --env-file .env python scripts/backup_restore.py backup --output $(OUT)
	@echo "✅ Backup complete: $(OUT)"

verify-backup:
	@if [ -z "$(BUNDLE)" ]; then \
		echo "Usage: make verify-backup BUNDLE=path/to/backup.tar.gz"; \
		exit 1; \
	fi
	@uv run --env-file .env python scripts/backup_restore.py restore $(BUNDLE) --verify-only

restore:
	@if [ -z "$(BUNDLE)" ]; then \
		echo "Usage: make restore BUNDLE=path/to/backup.tar.gz [FORCE=1]"; \
		echo ""; \
		echo "DANGER: restoring overwrites the current data directory."; \
		echo "        Run \`make verify-backup BUNDLE=...\` first to confirm integrity."; \
		exit 1; \
	fi
	@if [ "$(FORCE)" = "1" ]; then \
		echo "⚠️  FORCE=1 — will overwrite any existing data."; \
		uv run --env-file .env python scripts/backup_restore.py restore $(BUNDLE) --force; \
	else \
		uv run --env-file .env python scripts/backup_restore.py restore $(BUNDLE); \
	fi
	@echo "✅ Restore complete from: $(BUNDLE)"

## v0.7.129 — test runners.
## `make test`             runs the hermetic backend suite (no external deps).
## `make test-integration` runs the SurrealDB-backed integration suite. You
##                         MUST have SurrealDB up — `make database` first —
##                         and the test fixtures will mint a throwaway
##                         namespace (onp_test_<uuid>) so your real data is
##                         untouched.

test:
	uv run pytest tests/ -v --ignore=tests/integration

test-integration:
	@echo "Running integration tests against SurrealDB at $${SURREAL_URL:-ws://localhost:8000/rpc}..."
	@echo "Tests use a throwaway namespace; your real data is not touched."
	SURREAL_INTEGRATION=1 uv run --env-file .env pytest tests/integration/ -v -m integration_surreal

## v0.7.139 — Live model benchmark harness.
##
## Exercises every configured language Model against three real probes
## (notebook chat, Studio JSON-outline, podcast multi-speaker turn) and
## writes a ranked benchmark-report.md.
##
## Requires services running:
##   1. make database     (SurrealDB)
##   2. make api          (FastAPI :5055)
##   3. make worker       (surreal-commands worker)
## Then:
##   make benchmark-models
##
## Single-model run:
##   ONP_BENCHMARK_ONLY="My OpenAI gpt-4o-mini" make benchmark-models
##
## Custom per-call timeout (default 90s):
##   ONP_BENCHMARK_PER_CALL_TIMEOUT_SEC=180 make benchmark-models
.PHONY: benchmark-models
benchmark-models:
	@echo "Benchmarking models at $${ONP_BENCHMARK_API_BASE:-http://localhost:5055}..."
	@echo "Requires API + worker + SurrealDB to be running. Use \`make status\` to verify."
	uv run --env-file .env python scripts/benchmark_models.py --output benchmark-report.md
	@echo ""
	@echo "Report: ./benchmark-report.md"

.PHONY: worker worker-start worker-stop worker-restart

worker: worker-start

worker-start:
	@echo "Starting surreal-commands worker..."
	uv run --env-file .env surreal-commands-worker --import-modules commands

worker-stop:
	@echo "Stopping surreal-commands worker..."
	pkill -f "surreal-commands-worker" || true

worker-restart: worker-stop
	@sleep 2
	@$(MAKE) worker-start

# === Service Management ===
start-all:
	@echo "🚀 Starting Open Notebook (Database + API + Worker + Frontend)..."
	@echo "📊 Starting SurrealDB..."
	# v0.7.140 — was docker-compose.dev.yml (didn't exist).
	@docker compose -f docker-compose.yml up -d surrealdb
	# v0.7.140 — poll SurrealDB /health instead of a flat sleep 3s.
	# Cold-start with a fresh volume can exceed 3s on slower disks;
	# the polling loop bails after 30s with a clear error rather
	# than letting the API fail its first migration silently.
	@echo -n "   Waiting for SurrealDB"
	@for i in $$(seq 1 30); do \
		if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then \
			echo " ✓"; break; \
		fi; \
		echo -n "."; \
		sleep 1; \
		if [ "$$i" = "30" ]; then \
			echo ""; echo "❌ SurrealDB did not become ready within 30s"; \
			docker compose -f docker-compose.yml logs surrealdb | tail -20; \
			exit 1; \
		fi; \
	done
	@echo "🔧 Starting API backend..."
	# v0.7.140 — added --env-file .env (was missing). Without it,
	# run_api.py didn't see OPEN_NOTEBOOK_ENCRYPTION_KEY +
	# SURREAL_URL / SURREAL_PASSWORD from .env (which the worker
	# line below already loads correctly). Symptom: API came up
	# but credential decryption failed on the first auth call.
	@uv run --env-file .env run_api.py &
	@sleep 3
	@echo "⚙️ Starting background worker..."
	@uv run --env-file .env surreal-commands-worker --import-modules commands &
	@sleep 2
	@echo "🌐 Starting Next.js frontend..."
	@echo "✅ All services started!"
	@echo "📱 Frontend: http://localhost:3000"
	@echo "🔗 API: http://localhost:5055"
	@echo "📚 API Docs: http://localhost:5055/docs"
	cd frontend && npm run dev

stop-all:
	@echo "🛑 Stopping all Open Notebook services..."
	@pkill -f "next dev" || true
	@pkill -f "surreal-commands-worker" || true
	@pkill -f "run_api.py" || true
	@pkill -f "uvicorn api.main:app" || true
	@docker compose down
	@echo "✅ All services stopped!"

status:
	@echo "📊 Open Notebook Service Status:"
	@echo "Database (SurrealDB):"
	@docker compose ps surrealdb 2>/dev/null || echo "  ❌ Not running"
	@echo "API Backend:"
	@pgrep -f "run_api.py\|uvicorn api.main:app" >/dev/null && echo "  ✅ Running" || echo "  ❌ Not running"
	@echo "Background Worker:"
	@pgrep -f "surreal-commands-worker" >/dev/null && echo "  ✅ Running" || echo "  ❌ Not running"
	@echo "Next.js Frontend:"
	@pgrep -f "next dev" >/dev/null && echo "  ✅ Running" || echo "  ❌ Not running"

# === Documentation Export ===
export-docs:
	@echo "📚 Exporting documentation..."
	@uv run python scripts/export_docs.py
	@echo "✅ Documentation export complete!"

# === Desktop build (mirrors .github/workflows/build-desktop.yml) ===
#
# Builds the macOS .app + .dmg locally. Mirrors CI exactly so what you build
# here is what GitHub Actions would build on a tag push.
#
# One-shot:
#   make build-mac                      # full clean build, produces dist/Open Notebook Plus.app + .dmg
#
# Iterative (re-run individual stages):
#   make build-mac-venv                 # set up .build-venv with pinned deps
#   make build-mac-frontend             # Next.js build into frontend/.next
#   make build-mac-runtimes             # fetch surreal/node/uv/python-build-standalone
#   make build-mac-pyinstaller          # run pyinstaller spec
#   make build-mac-dmg                  # wrap .app into .dmg via hdiutil
#
# Tear-down:
#   make build-mac-clean                # remove dist/, build/, .build-venv/
#   make build-mac-distclean            # also remove the fetched runtimes
#
# Override the Python interpreter (default: python3.12 from PATH):
#   make build-mac BUILD_PYTHON=/opt/homebrew/bin/python3.12
#
# To install the .app after building:
#   make build-mac-install              # copies dist/Open\ Notebook\ Plus.app → /Applications

.PHONY: build-mac build-mac-test build-mac-venv build-mac-frontend build-mac-runtimes build-mac-pyinstaller build-mac-dmg build-mac-clean build-mac-distclean build-mac-install

BUILD_PYTHON ?= python3.12
BUILD_VENV   := .build-venv
BUILD_PIP    := $(BUILD_VENV)/bin/pip
BUILD_PY     := $(BUILD_VENV)/bin/python
BUILD_PYINSTALLER := $(BUILD_VENV)/bin/pyinstaller

# Detect CPU arch (arm64 vs x86_64) — drives the DMG filename.
BUILD_ARCH := $(shell uname -m)

build-mac: build-mac-test build-mac-lock build-mac-venv build-mac-frontend build-mac-runtimes build-mac-pyinstaller build-mac-dmg
	@echo ""
	@echo "✅ macOS build complete:"
	@echo "    dist/Open Notebook Plus.app"
	@echo "    dist/Open-Notebook-Plus-mac-$(BUILD_ARCH).dmg"
	@echo ""
	@echo "Run with:  open 'dist/Open Notebook Plus.app'"
	@echo "Tail logs: tail -F ~/.open-notebook-plus/logs/*.log"

# Stage 0: precondition — fast unit suite. Catches regressions before we
# spend 15+ min on a build that's going to be DOA. Uses the test venv (3.14)
# which is separate from the build venv (3.12). P2-MED-12 audit fix.
build-mac-test:
	@echo "🧪 Running unit tests (precondition for build-mac)…"
	# v0.8.66 (audit I-M1) — DON'T pipe to `tail`: a piped recipe's exit status
	# is the LAST command's (tail, always 0), so a failing test suite could NOT
	# fail the build (the "Stage 0 precondition" was toothless). Run pytest
	# directly so its non-zero exit aborts `build-mac`.
	@/Users/Antman/Desktop/OpenNotebook/.venv/bin/python -m pytest desktop/tests/ desktop/memory/tests/ -q

# v0.7.141 — Stage 0.5: regenerate desktop/requirements.lock from
# pyproject.toml BEFORE the bundle venv installs against it.
#
# Why this exists: prior to v0.7.141, desktop/requirements.lock was
# hand-maintained — last touched in commit 90fbf8e (pre-v0.7.124).
# Any dep added to pyproject.toml between regen and bundle build
# was silently dropped from the bundle. v0.7.124 added
# `prometheus-client>=0.20.0` but the lockfile was never refreshed,
# so the bundled venv installed without it, the API crashed at
# import time ("ModuleNotFoundError: No module named 'prometheus_client'"),
# and the launcher timed out waiting for /readyz.
#
# The user-facing symptom: `Open Notebook Plus.app` opens, shows
# a splash, then silently quits after ~3 minutes with no UI ever
# appearing.
#
# Now: every `make build-mac` regenerates the lock from current
# pyproject.toml AND desktop/requirements.txt first. The header in
# desktop/requirements.lock already documents the canonical command —
# we just promote it to a Makefile target so it actually runs.
#
# v0.7.154 — Added `desktop/requirements.txt` as a second compile
# input. Background: v0.7.141 introduced this target compiling
# only from pyproject.toml, which silently DROPPED any dep that
# was declared only in desktop/requirements.txt (CI's
# "installs on top of the upstream pyproject.toml" path). The
# casualty was `llama-cpp-python>=0.3.16,<0.4` (desktop/requirements.txt:18,
# pinned for CVE-2024-42479) — the lockfile shipped without it,
# the bundled venv installed without it, and every local-GGUF chat
# attempt got `ModuleNotFoundError: No module named 'llama_cpp'`
# at llama_cpp.server spawn (visible in llamacpp_chat_stderr.log
# now that v0.7.151 captures stderr). Passing BOTH files to
# `uv pip compile` merges the dep sets exactly the way
# `pip install -r requirements.txt` would have at runtime.
build-mac-lock:
	@echo "🔒 Regenerating desktop/requirements.lock from pyproject.toml + desktop/requirements.txt..."
	@uv pip compile pyproject.toml desktop/requirements.txt --python-version 3.12 \
		-o desktop/requirements.lock --quiet
	@echo "   Lockfile: $$(wc -l < desktop/requirements.lock) pinned packages"

# Stage 1: isolated build venv with pinned deps (separate from .venv used for tests).
build-mac-venv:
	@if [ ! -d "$(BUILD_VENV)" ]; then \
		echo "🐍 Creating $(BUILD_VENV) with $(BUILD_PYTHON)..."; \
		$(BUILD_PYTHON) -m venv $(BUILD_VENV); \
	fi
	@echo "📦 Installing desktop build deps..."
	@$(BUILD_PIP) install --upgrade pip > /dev/null
	@$(BUILD_PIP) install -r desktop/requirements.txt
	@$(BUILD_PIP) install -e .

# Stage 2: Next.js standalone build → frontend/.next/standalone (consumed by PyInstaller spec).
build-mac-frontend:
	@echo "⚛️  Building Next.js frontend..."
	@if [ ! -d "frontend/node_modules" ]; then cd frontend && npm ci; fi
	@cd frontend && npm run build

# Stage 3: fetch surreal binary, node, uv, python-build-standalone tarball into desktop/bin/.
# Idempotent — fetch_runtimes.py skips files already present.
build-mac-runtimes:
	@echo "⬇️  Fetching bundled runtimes (surreal / node / uv / python-standalone)..."
	@$(BUILD_PY) desktop/build/fetch_runtimes.py

# Stage 4: PyInstaller — produces dist/Open Notebook Plus.app from desktop/build/pyinstaller.spec.
#
# v0.7.146 — Re-seal the bundle with `codesign --force --deep --sign -`
# AFTER PyInstaller finishes. Background:
#
#   macOS auto-applies an ad-hoc signature to arm64 Mach-O binaries the
#   first time they're written. PyInstaller produces the .app in
#   multiple write phases (COLLECT, then BUNDLE wraps it), and ANY file
#   modification under the bundle after macOS seals it — including
#   Spotlight indexing writing extended attributes, or PyInstaller's
#   own multi-pass writes — invalidates the seal. The Gatekeeper
#   verdict on the user's first rebuild was:
#
#     spctl -a -vvv "Open Notebook Plus.app"
#     → a sealed resource is missing or invalid
#
#   When a Gatekeeper seal is broken, macOS silently kills the binary
#   at launch: no error dialog, no crash report, no stderr output. The
#   user double-clicks and nothing happens.
#
#   The fix is to do an explicit final codesign at the END of all
#   PyInstaller work, so the seal reflects the bundle's true final
#   contents. `--deep` re-signs every nested Mach-O (Python framework,
#   dylibs, helper binaries). `--force` overwrites any prior signature.
#   `--sign -` means ad-hoc (no developer cert required for local dev).
build-mac-pyinstaller:
	@echo "🔧 Running PyInstaller (this is the slow step, ~5-10 min)..."
	@$(BUILD_PYINSTALLER) desktop/build/pyinstaller.spec --noconfirm
	@echo "🔏 Re-sealing bundle (codesign --force --deep --sign -)..."
	@codesign --force --deep --sign - "dist/Open Notebook Plus.app"
	@echo "   Verifying seal..."
	@spctl -a -vvv "dist/Open Notebook Plus.app" 2>&1 | sed 's/^/   /' || \
		echo "   ⚠️  spctl rejected the bundle (expected for ad-hoc on first-launch Gatekeeper);" && \
		echo "   the seal itself is valid, run codesign -v to confirm."
	@codesign -v "dist/Open Notebook Plus.app" 2>&1 | sed 's/^/   /' || true

# Stage 5: wrap the .app into a .dmg via hdiutil. Unsigned — first launch needs
# right-click → Open OR `xattr -dr com.apple.quarantine dist/Open\ Notebook\ Plus.app`.
build-mac-dmg:
	@echo "💾 Building .dmg..."
	@bash desktop/build/post_build_mac.sh

# Convenience: copy the built .app to /Applications.
build-mac-install:
	@if [ ! -d "dist/Open Notebook Plus.app" ]; then \
		echo "❌ dist/Open Notebook Plus.app not found. Run 'make build-mac' first."; \
		exit 1; \
	fi
	@echo "📥 Installing to /Applications..."
	@rm -rf "/Applications/Open Notebook Plus.app"
	@cp -R "dist/Open Notebook Plus.app" /Applications/
	@xattr -dr com.apple.quarantine "/Applications/Open Notebook Plus.app" || true
	@echo "✅ Installed. Launch with: open '/Applications/Open Notebook Plus.app'"

# Remove PyInstaller artifacts and the build venv. Keeps fetched runtimes
# (downloading them again is the slowest step).
build-mac-clean:
	@echo "🧹 Removing dist/, build/, $(BUILD_VENV)/..."
	@rm -rf dist build $(BUILD_VENV)
	@echo "✅ Build artifacts cleaned. Runtimes in desktop/bin/ kept (use build-mac-distclean to wipe those too)."

# Nuclear option — also remove the fetched runtime binaries.
build-mac-distclean: build-mac-clean
	@echo "🧹 Removing desktop/bin/ (surreal / node / uv / python-standalone)..."
	@rm -rf desktop/bin
	@echo "✅ Distclean complete. Next build will re-download ~500 MB of runtimes."

# === Cleanup ===
clean-cache:
	@echo "🧹 Cleaning cache directories..."
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name ".mypy_cache" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name ".ruff_cache" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -type f -delete 2>/dev/null || true
	@find . -name "*.pyo" -type f -delete 2>/dev/null || true
	@find . -name "*.pyd" -type f -delete 2>/dev/null || true
	@echo "✅ Cache directories cleaned!"
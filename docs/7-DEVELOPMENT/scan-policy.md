# Source Scan Policy

Deeper Notebook source scans should stay inside this repository:

`/Users/Antman/Desktop/OpenNotebook/open-notebook-Plus`

Generated knowledge packs and project notes belong outside the repo under:

`/Users/Antman/BrainPulseKnowledge`

Local model inventory work belongs under:

`/Users/Antman/Desktop/AI_Models`

## What To Scan

- Application source under `api/`, `commands/`, `desktop/`, `frontend/src/`, `open_notebook/`, `scripts/`, and `tests/`.
- Project documentation under `docs/`, `README.md`, `README.dev.md`, and Plus-specific changelog files.
- Migration files, schemas, router contracts, and test fixtures that define current behavior.

## What To Ignore

The root `.codex-scanignore` excludes generated app output, caches, packaged installers, local runtime state, local databases, and model weights. This keeps scans fast and prevents generated artifacts from being mistaken for source.

Important ignored areas include:

- `desktop/build/`
- `frontend/.next/`
- `frontend/node_modules/`
- Python caches and virtual environments
- packaged `.dmg`, `.exe`, archive, and installer output
- local database/runtime state
- model files such as `.gguf`, `.safetensors`, `.bin`, and `.onnx`

## Safety Rules

- Do not scan or document other projects while using the Deeper Notebook knowledge-builder configuration.
- Do not include secrets, tokens, passwords, private keys, or `.env` values in generated notes.
- Do not delete existing notes or source files during a scan.
- Append dated updates under `BrainPulseKnowledge` instead of overwriting prior project knowledge.
- Treat native desktop usage as the primary user path; Docker is development/server infrastructure, not the user-facing Plus runtime.

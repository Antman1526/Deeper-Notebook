# Scripts Documentation

## upstream_sync_guard.sh

Creates a safe path for importing updates from `lfnovo/open-notebook` without
overwriting Open Notebook Plus work.

### What It Does

- Disables accidental pushes to the `upstream` remote.
- Fetches upstream updates read-only.
- Writes a safety snapshot under `output/upstream-sync/` before any merge work.
- Refuses to start an integration merge while the current worktree is dirty.
- Creates a separate integration worktree when the checkout is clean.

### Usage

```bash
# Snapshot current state and prepare an integration worktree if clean
scripts/upstream_sync_guard.sh prepare

# Only create a local safety snapshot, even when upstream/network is unavailable
scripts/upstream_sync_guard.sh snapshot

# Only compare branch divergence and upstream file churn
scripts/upstream_sync_guard.sh compare
```

See `docs/7-DEVELOPMENT/upstream-sync.md` for the full process.

## export_docs.py

Consolidates markdown documentation files for use with ChatGPT or other platforms with file upload limits.

### What It Does

- Scans all subdirectories in the `docs/` folder
- For each subdirectory, combines all `.md` files (excluding `index.md` files)
- Creates one consolidated markdown file per subdirectory
- Saves all exported files to `doc_exports/` in the project root

### Usage

```bash
# Using Makefile (recommended)
make export-docs

# Or run directly with uv
uv run python scripts/export_docs.py

# Or run with standard Python
python scripts/export_docs.py
```

### Output

The script creates `doc_exports/` directory with consolidated files like:

- `getting-started.md` - All getting-started documentation
- `user-guide.md` - All user guide content
- `features.md` - All feature documentation
- `development.md` - All development documentation
- etc.

Each exported file includes:
- A main header with the folder name
- Section headers for each source file
- Source file attribution
- The complete content from each markdown file
- Visual separators between sections

### Example Output Structure

```markdown
# Getting Started

This document consolidates all content from the getting-started documentation folder.

---

## Installation

*Source: installation.md*

[Full content of installation.md]

---

## Quick Start

*Source: quick-start.md*

[Full content of quick-start.md]

---
```

### Notes

- The `doc_exports/` directory is gitignored and safe to regenerate anytime
- Index files (`index.md`) are automatically excluded
- Files are sorted alphabetically for consistent output
- The script handles subdirectories only (ignores files in the root `docs/` folder)

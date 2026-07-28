# Second Brain read-only scan protocol

Status: reusable protocol only. This document does not claim that a private
vault was mounted, scanned, or verified.

Run the verifier only with an explicit vault root supplied by the owner. It
rejects the filesystem root, the current user's home directory, and paths that
are not directories. It resolves `--output` before observing or writing
anything and rejects an output equal to, inside, or symlink-resolved inside the
source root. `--check-only` validates the root, output, source inventory, Git
state capture, and connector-manifest counts without making API calls.

For a controlled verification, the script registers the approved mixed parent
and its Obsidian and Logseq children through the canonical Deeper Notebook
vault API. It imports only the root-relative connector manifest as trust
metadata, then performs two scans. Before and after each scan it compares
regular-file SHA-256 inventories and Git porcelain state. If Git status is
blocked by a pre-existing lock, the report records `git_status_unavailable`; it
does not alter the lock or repository. A mismatch stops before the next scan,
writes a sanitized failure report, and returns nonzero.

When a mount has the approved name already, the verifier fetches its owner-safe
detail and requires the exact resolved root path, format, parent relationship,
and watch state before reusing its ID. A conflicting or ambiguous matching name
fails safely and is never scanned or used for trust import. Trust reconciliation
compares each synthesis record's `derived_from` array to the connector manifest
by stable record ID, including array order and membership.

The generated report is intentionally structured and sanitized. It contains a
root label, relative file paths and hashes, count reconciliation, and failure
codes only. It excludes source contents, secrets, absolute source paths, and
unredacted home paths. A successful controlled report requires unchanged source
hashes and Git state, zero projections changed on the second scan, matching
trust totals, and exact retained `derivedFrom` arrays for every synthesis
record.

Example owner-invoked command:

```bash
uv run python scripts/verify_read_only_vault.py \
  --root "/approved/external-vault" \
  --api "http://127.0.0.1:5055/api/deeper-notebook" \
  --output "docs/verification/2026-07-26-second-brain-read-only-scan.json"
```

Treat the generated report as proof only for the exact run it describes. The
synthetic tests in `tests/test_verify_read_only_vault.py` cover the protocol
without accessing any private vault.

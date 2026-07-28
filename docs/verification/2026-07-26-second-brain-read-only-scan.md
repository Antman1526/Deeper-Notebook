# Second Brain read-only scan protocol

Status: reusable protocol only. This document does not claim that a private
vault was mounted, scanned, or verified.

Run the verifier only with an explicit vault root supplied by the owner. It
rejects the filesystem root, the current user's home directory, and paths that
are not directories. Immediately after validation it binds the resolved root
path to its device/inode identity. Before and after every source snapshot around
an API operation, and again immediately before report creation, the supplied
root path must still resolve to that same directory identity. A rename, symlink
rebind, or replacement fails closed without creating a report. It resolves
`--output` before observing or writing anything and rejects an output equal to,
inside, or symlink-resolved inside the source root. Immediately before report
creation it resolves the output again and confirms it remains outside the
stable root identity. The report target must not already exist: it is created
once with exclusive creation and owner-only permissions, so an existing file or
hard link can never be truncated. Its parent directory identity is rechecked
immediately before creation to fail closed if a path changes during the run.
`--check-only` validates the root, output, source inventory, Git
state capture, and connector-manifest counts without making API calls.

For a controlled verification, the script registers the approved mixed parent
and its Obsidian and Logseq children through the canonical Deeper Notebook
vault API. It imports only the root-relative connector manifest as trust
metadata, then performs two scans. The canonical connector manifest uses its
`documents` array; the verifier accepts the legacy `records` array only when it
is the sole supported record array. A manifest with both arrays, no usable array,
or malformed record IDs/evidence classes fails closed. It reads only each
record's `id`, `evidenceClass`, and (for synthesis records) `derivedFrom` fields;
all other manifest fields are ignored and never enter the report. The source inventory walks every regular,
non-symlink file below the explicit root except `.git/**`; this includes files
ignored by Git and untracked files. Git porcelain remains supplementary rather
than deciding which files are fingerprinted. Every canonical API request
(mount list, create, detail/reuse, trust import, scans, trust, summary, and
receipts) receives a before/after source reconciliation. A changed source is
recorded immediately and terminates the run, even if the API response is
malformed or failed after a side effect. If Git status is
blocked by a pre-existing lock, the report records `git_status_unavailable`; it
does not alter the lock or repository. A mismatch stops before the next scan,
writes a sanitized failure report, and returns nonzero.

The post-operation observation is mandatory even when an API request fails or
times out: every request is wrapped so the after snapshot runs in `finally`.
If a failed request changed source hashes or Git state, the report records the
observation mismatch before its sanitized operation failure. Filesystem, inventory,
subprocess, API, and report-creation failures are normalized to stable failure
codes or a generic user-facing error; they do not expose source paths, source
contents, or tracebacks.

When a mount has the approved name already, the verifier fetches its owner-safe
detail and requires the exact resolved root path, format, parent relationship,
and watch state before reusing its ID. A conflicting or ambiguous matching name
fails safely and is never scanned or used for trust import. Trust reconciliation
compares each synthesis record's `derived_from` array to the connector manifest
by stable record ID, including array order and membership. Those arrays are
untrusted provenance metadata: they stay internal for exact comparison and the
report exposes only aggregate counts plus a SHA-256 provenance digest, never
their values.

The vault-list response itself must be a list. Every ID, including an ID just
returned by mount creation, is fetched from the canonical detail endpoint and
must match the normalized root, name, format, parent, and watch setting before
trust import or scanning can begin.

The generated report is intentionally structured and sanitized. It contains a
root label, relative file paths and hashes, count reconciliation, digest-only
provenance, and failure codes only. It excludes source contents, secrets,
absolute source paths, unredacted home paths, raw `derivedFrom` values, and all
other connector-manifest fields (including source/content paths, titles, and
vault roots). A successful controlled report requires unchanged source
hashes and Git state, zero projections changed on the second scan, matching
trust totals, and exact internally-reconciled `derivedFrom` arrays for every
synthesis record.

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

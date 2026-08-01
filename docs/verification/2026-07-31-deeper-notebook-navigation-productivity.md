# Deeper Notebook navigation productivity verification

## Verdict

Mock and synthetic verifier gates passed. Persistent API, SurrealDB, and native
macOS gates are blocked pending explicitly caller-launched persistent services.

## Baseline and commit

Task 12 verifier is local-only and rejects real Second Brain roots.

## Mocked browser evidence

Task 11 production-mocked browser coverage passed: bookmarks, Random Note,
metrics keyboard command, named workspace restore, stale-target confirmation,
conflict refresh, and focus return.

## Persistent local API evidence

Blocked: no caller-launched persistent API was supplied for this record.

## SurrealDB migration and restart evidence

Blocked: run only with `SURREAL_INTEGRATION=1` against the shared isolated
integration namespace; no disposable database was started.

## Native macOS evidence

Blocked: no caller-launched native application smoke was supplied.

## External authority and source-fingerprint evidence

The verifier creates only temporary synthetic Obsidian, Logseq, and app-owned
Overlay fixtures, reports aggregate hashes/counts, and records zero external
writes. It never reads or writes a real Second Brain root.

## Remaining gates

Provide persistent API/SurrealDB/native processes, then run the verifier with a
new temporary fixture root and preserve its untracked redacted JSON report.

## 2026-07-31 controlled persistent-runtime rerun

### Verdict update

The persistent API and real-SurrealDB gates passed in caller-launched,
disposable local processes. The aggregate verifier remains intentionally
`blocked`: it correctly requires a separately observed packaged native macOS
application smoke before it can report overall success.

### Persistent API evidence

- The API `GET /readyz` returned HTTP 200 with an online database, applied
  migrations, and no pending migrations.
- The verifier used its generated synthetic fixture only and returned its
  expected exit code `2` (aggregate blocked). Its `persistent_api` gate passed
  at HTTP 200, `source_hashes_unchanged` was true, and `external_writes` was
  zero.
- The verifier was corrected to query the native API's direct `/health`
  endpoint. The previous `/api/health` path belongs to the frontend proxy and
  returns 404 when the backend is contacted directly.

### Real SurrealDB evidence

- The opt-in integration tests ran with `SURREAL_INTEGRATION=1` against fresh,
  disposable namespaces under the caller-launched local SurrealDB runtime.
- The knowledge-engine projection and vault-projection suites completed with
  no retained pytest failures after their migration-39 expectations were
  aligned.
- The tests exercise migration rollback and re-application, replay,
  persistence/reconstruction, and vault projection behavior. The migration-39
  bookmark and named-workspace tables are included in the native schema
  assertion.

### Shutdown receipt

The API completed its normal shutdown sequence and closed its SurrealDB pool;
the proof-owned SurrealDB process then received SIGINT and exited. No listener
remained on either proof port.

### Still required

- Windows installer build, install, upgrade, repair, and uninstall proof on a
  Windows runtime.

## 2026-07-31 isolated packaged-macOS vault proof

### Result

The packaged `Deeper Notebook.app` passed the isolated read-only vault
restart/mount/index/graph/search proof using an app-owned synthetic fixture.
The fixture was created outside every real Second Brain root; the exercised
routes performed no external-file writes.

### Packaged restart evidence

- The application was launched with a fresh disposable `HOME` and
  `USERPROFILE`. Its readiness receipt reported a local API, online SurrealDB,
  and applied/no-pending migrations.
- A two-file synthetic Obsidian fixture mounted with `watch_enabled: false`.
  The first scan records pending observations by design; the stable follow-up
  scan parsed both files, and a repeated scan projected no additional changes.
- The page route retained each SHA-256 source fingerprint, resolved both
  wikilinks, and exposed the expected task and front-matter metadata.
- The graph route returned the two expected nodes and two wikilink edges.
  Text search for the known fixture token returned `Linked Note` with
  `canonical_external: true`, its vault ID, relative path, and source hash.
- The proof-owned app process received a graceful `SIGTERM`; no packaged API
  or SurrealDB child process or listener remained. A second native launch with
  the same isolated profile restored the read-only mount, both parsed files,
  hashes, graph, and provenance-bearing search result.

### Observed caveats

- On the first cold packaged launch, the renderer displayed its load-error
  page until an explicit Reload, after which the dashboard loaded. This is a
  release-quality issue to reproduce and repair separately; it does not
  invalidate the API persistence evidence above.
- An earlier registration attempt rooted in the worktree timed out and left
  that API instance unresponsive. The same packaged validator approved the
  path, but the issue was not characterized further. Repeating the proof with
  a separately owned, safe home-directory fixture succeeded; do not treat the
  worktree-root behavior as resolved.

## 2026-07-31 legacy data-root upgrade regression

The focused legacy upgrade and recovery suite passed: 96 tests covering
same-volume atomic migration, durable pre-move receipts, critical-file hashes,
rollback safety, non-equivalent-root recovery with zero writes, and reversible
macOS app replacement logic. This is strong code-level evidence only; a native
legacy-profile upgrade smoke and the Windows installer lifecycle remain release
gates.

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

- A genuinely isolated packaged macOS restart/mount/index/search proof.
- Windows installer build, install, upgrade, repair, and uninstall proof on a
  Windows runtime.

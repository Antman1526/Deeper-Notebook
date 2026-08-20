# 14 — Security Implementation & Best Practices

> **Current posture (2026-08-17):** Bandit HIGH in project code **0**; B608 findings
> **0** (down from 79); remaining project MEDIUMs **4**, all triaged false positives;
> pip-audit residuals **2**, both with documented reasons. Full triage:
> `docs/verification/2026-08-16-security-scan.md`.

---

## 1. Threat model

Single-user, local-first desktop app; all services bind `127.0.0.1`. Real adversaries:

1. **Malicious content** — a hostile PDF, web page, or vault file
2. **Model-directed action** — the LLM induced to fetch or ingest something
3. **Supply chain** — a dependency shipping a vulnerability
4. **Local processes** — other software on the machine

Not in scope: multi-tenant isolation, network attackers (nothing listens off-loopback).

## 2. SSRF boundary (fail-closed)

`deeper_notebook/security/outbound_url.py` validates any user- or model-controlled URL:

```python
MAX_URL_LENGTH = 2_048
ALLOWED_SCHEMES = frozenset({"http", "https"})


def _canonical_hostname(hostname: str) -> str:
    if not hostname or "%" in hostname or "\\" in hostname:
        _reject("URL hostname is malformed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        # Python's URL parser accepts legacy numeric forms that network stacks
        # interpret as IP literals. Refuse them instead of guessing.
        if hostname.lower().startswith("0x") or all(
            char in "0123456789abcdefABCDEFxX." for char in hostname
        ):
            _reject("URL hostname uses a non-canonical IP address")
        canonical = hostname.encode("idna").decode("ascii").lower()
        ...
```

It resolves and checks **every** returned address (`ValidatedOutboundURL.addresses`), so
DNS rebinding into a private range is refused. Deliberately distinct from the MCP/credential
validator — a localhost MCP server is legitimate; a web source reaching localhost is not.

Model-callable ingestion routes both branches through the boundary:

```python
if url_engine == "crawl4ai":
    checked_response = await fetch_public_url(url)  # fetch once, through policy
    content = await extract_url_with_crawl4ai(url, prefetched=checked_response)
if processed_state is None:
    # Do not delegate a raw URL to content-core, whose fetcher has a
    # different localhost policy.
    processed_state = await _extract_checked_url(content_state)
```

## 3. SurrealQL injection defence

**Contract:** identifiers may be interpolated only after whitelist validation; values
always travel as `$`-bound parameters.

The B608 burn-down (79 → 0) audited every flagged site. One was genuinely weak and was
**fixed**, not annotated:

```python
# api/command_service.py — v0.8.87
# Parse before interpolating: RecordID.parse rejects anything that is not a
# well-formed record id, so a hostile job_id cannot smuggle SurrealQL.
record_id = ensure_record_id(
    job_id if job_id.startswith("command:") else f"command:{job_id}"
)
```

The remaining 78 were verified and carry inline `# nosec B608` tags. Placement is
**AST-guarded** — a naive end-of-line append lands *inside* a multiline f-string query and
becomes query text:

```python
candidate[i] = candidate[i] + TAG
if ast.dump(ast.parse("\n".join(candidate))) != baseline:
    continue  # tag would alter a string constant → try the closing line instead
```

Validated-identifier example:

```python
allowed_fields = {"name", "created", "updated"}
allowed_directions = {"asc", "desc"}
# ... parts checked, HTTPException(400) otherwise ...
```

Vector ids pass `_validate_vector_id`; memory ids pass a character whitelist with a
dedicated injection suite (`abc'; DROP TABLE memory_fact;`, newlines, `abc:other_id`,
empty — each must 4xx and `mem.delete` must never be called).

## 4. XML/entity hardening

```python
_MAX_ARXIV_BYTES = 5_000_000
if xml_text and len(xml_text) > _MAX_ARXIV_BYTES:
    logger.warning("arxiv feed exceeded {} bytes; discarded", _MAX_ARXIV_BYTES)
    return []
root = ElementTree.fromstring(xml_text or "")  # nosec B314 - bounded, no entity resolution
```

stdlib `etree` does not resolve external entities; bounding the payload closes the
remaining expansion-DoS concern.

## 5. Archive extraction

```python
with tarfile.open(tarball, "r:gz") as t:
    validate_tar_members(t, expected_root="python")  # path-traversal defence
    t.extractall(runtime_dir, filter="data")  # nosec B202 - validated above
```

Every downloaded runtime is SHA-256 verified with `hmac.compare_digest` before use, and
staged-then-atomically-replaced so a failed download can't clobber a verified artifact.

## 6. Encryption at rest

Provider keys are encrypted in the `credential` table.

```
DEEPER_NOTEBOOK_ENCRYPTION_KEY=      # required, ≥16 chars
DEEPER_NOTEBOOK_ENCRYPTION_KEYS=new,old    # rotation without re-entering credentials
DEEPER_NOTEBOOK_ENCRYPTION_KDF=
```

Rotation exists because the alternative — re-entering a dozen keys — guarantees nobody
rotates. `*_FILE` indirection supports Docker secrets.

## 7. Desktop shell hardening

```python
desired = {
    "OPEN_EXTERNAL_LINKS_IN_BROWSER": True,
    "ALLOW_DOWNLOADS": False,
    "OPEN_DEVTOOLS_IN_DEBUG": False,
}
```

Only keys the installed pywebview defines are set (forward-compatible). The JS bridge
exposes exactly one method (`relaunch`). The shell loads only the local Next origin; the
sole third-party in-window content is a YouTube iframe for YouTube sources.

## 8. Code signing

A **stable** self-signed identity keeps macOS TCC grants across rebuilds. Two script bugs
worth recording:

- Self-signed certs must be trusted with `-r trustRoot`; `trustAsRoot` errors with
  "parameters not valid" and leaves the identity `CSSMERR_TP_NOT_TRUSTED`.
- Existence checks must **not** use `find-identity -v`, which hides untrusted identities —
  causing duplicate imports plus a false "not found" failure.

Not notarized (owner decision). First launch of a fresh DMG needs right-click → Open.

## 9. Product-identity governance

`scripts/rebrand_audit.py` (2,896 lines) classifies every legacy-name occurrence into
`compatibility_alias`, `historical_reference`, `migration_documentation`,
`upstream_reference`, or `unexpected_active_identity` — the last fails the build.

Current: `829 / 1749 / 588 / 99 / 0`, zero stale entries.

**The registry is line-pinned and self-validating.** Entries key on
`(path, pattern, source, line, column, context_sha256)`, and contracts are loaded from the
allowlist itself, so hand-editing fails `load_allowlist` with *"compatibility entry must
use its exact canonical compatibility contract"*.

Operational rules learned twice this project:

1. Any edit that shifts a pinned line breaks the audit. Prefer layout that preserves line
   numbers (pack additions onto existing lines; put new helpers **below** pinned lines).
2. `--regenerate` must be the **last** step after all edits — running it mid-edit re-keys
   to a layout that then moves again.
3. Re-run `--check` before any commit touching pinned files or locks.

## 10. Dependency security

```make
security-scan:
	@uvx bandit -r deeper_notebook api desktop \
	  -x "desktop/bin,desktop/tests,desktop/memory/tests" -q --severity-level high
	@uvx --python /opt/homebrew/bin/python3.12 pip-audit \
	  -r desktop/requirements.lock --no-deps || true
```

Fixed by floors: `h2>=4.4.1` (PYSEC-2026-3628), `joserfc>=1.6.8` (-2528/-2530),
`setuptools>=83.0.0` (-3447), plus `pytest>=9.0.3` (-1845) and `mem0ai>=2.0.18` (-2636).

Accepted residuals:

| Package | Advisory | Reason |
|---|---|---|
| pillow 11.3.0 | ~20 PYSECs | DN-DEP-PILLOW-2026-08-11: `podcast-creator → moviepy` requires `<12` |
| diskcache 5.6.3 | PYSEC-2026-2447 | No fixed release exists |

Triaged Bandit MEDIUMs (all false positives): `B108` (`/tmp` in a **denylist** of forbidden
roots), `B102` (build tool `exec`ing the repo's own version file), `B310` (`urlopen` on a
hardcoded `127.0.0.1`), `B314` (parsing the repo's own canonical SVG at build time).

## 11. Secret hygiene

`gitleaks` runs on staged changes before each commit and over the full push range. The
574-commit push scan returned exactly one finding: a high-entropy `idempotency_key`
assignment in `tests/test_podcast_studio_api.py` at `da240ab15d`. Reading the historical
blob confirmed it is a test fixture string, not a credential.

Note the second-order trap: writing that finding out verbatim in a document makes the
document itself trip the same rule. Describe such findings by location and verdict —
never by reproducing the literal.

Rules: never log key-bearing exception text; keep values out of env receipts; scan before
pushing history.

## 12. Checklist for new code

- [ ] User/model URL → `fetch_public_url` / `_extract_checked_url`
- [ ] Values `$`-bound; identifiers whitelisted; record ids via `ensure_record_id`
- [ ] Parsers size-bounded before parse
- [ ] Archive members validated before extract; digests verified
- [ ] No secret in a log line, including exception text
- [ ] Feature-guarded routes 404 **before** parsing input
- [ ] `make security-scan` clean; `rebrand_audit --check` exit 0

---

*Continues in [15 — File Structure & Code Organization](./15-file-structure-code-organization.md).*

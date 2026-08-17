# Security scan — 2026-08-16

First run of both scanners in this repository's recorded history. The Phase 2A
acceptance receipt listed both as environment-blocked exclusions; unblocked
today (`make security-scan`).

## Bandit (uvx bandit, project code, vendored desktop/bin excluded)

- HIGH severity: **0** (all 15 raw HIGHs were inside the vendored Node.js
  runtime's node-gyp Python files — third-party, excluded).
- MEDIUM: 84, of which 79 are B608 "SQL string composition" — the codebase's
  SurrealQL query-building pattern. These are guarded by boundary validation
  and dedicated injection tests (e.g. the memory-shim whitelist suite); a
  site-by-site burn-down is future work, not a current exposure claim.
- Remaining MEDIUMs, triaged:
  - B314 `scholarly_search.py` — **fixed**: arXiv payload now size-bounded
    (5 MB) before XML parsing; stdlib etree resolves no external entities.
  - B108 `vault/security.py` — false positive: "/tmp" appears in a
    *denylist* of forbidden roots.
  - B102 `release_manifest.py` — build tool exec()ing the repo's own
    version file; trusted input.
  - B310 `db_repair.py` — urlopen with a hardcoded `http://127.0.0.1` scheme.
  - B314 `make_icon.py` — parses the repo's own canonical SVG at build time.

## pip-audit (243 packages from desktop/requirements.lock)

Fixed today (floors added to desktop/requirements.txt, both locks regenerated):

| Package | Was | Now | Advisory |
|---|---|---|---|
| h2 | 4.3.0 | 4.4.1 | PYSEC-2026-3628 |
| joserfc | 1.6.5 | 1.7.4 | PYSEC-2026-2528/-2530 |
| setuptools | 82.0.1 | 84.0.0 | PYSEC-2026-3447 |

Accepted residuals (re-triage on dependency movement):

| Package | Advisory | Why accepted |
|---|---|---|
| pillow 11.3.0 | ~20 PYSECs, fixed in 12.x | Pre-existing documented exception DN-DEP-PILLOW-2026-08-11: podcast-creator → moviepy requires Pillow<12. Revisit when moviepy supports 12. |
| pytest 8.3.4 | PYSEC-2026-1845 | Dev/test tooling in the bundle venv, not exercised at runtime; pytest 9 requires a pytest-asyncio migration — separate change. |
| mem0ai 1.0.11 | PYSEC-2026-2636 | Only fix is 2.0.0b2 (beta of a major); memory layer is production-critical. Revisit at 2.0 stable. |
| diskcache 5.6.3 | PYSEC-2026-2447 | No fixed release exists. |

## Tooling notes

pip-audit must run under an interpreter with a working `ensurepip`; uv-managed
pythons ship without one, which is what the receipt's SIGABRT was. The make
target pins the Homebrew interpreter.

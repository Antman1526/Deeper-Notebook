# Dependency Hardening Batch

## Scope and authority

- Exact checkout: `/Users/Antman/Documents/Open Notebook/Deeper-Notebook`.
- Starting audit revision: `4c8b5a3d1fe4` plus the completed security/plugin
  batch that precedes this task.
- Preserve public APIs, schemas, user workflows, unrelated untracked state, and
  reproducible lockfiles. Do not perform opportunistic major framework rewrites.
- Use TDD/verification discipline; dependency changes require full adjoining
  and repository gates, not only a successful resolver.

## Reproduced baseline

- `npm audit --omit=dev --json`: one high advisory, `nanoid 3.3.16`, pulled by
  the explicit `postcss 8.5.24` override. Official npm registry reports
  `postcss 8.5.26` depends on `nanoid ^3.3.17`.
- `pip-audit --disable-pip` against the exported production lock: 82 advisory
  records across 21 packages. Fixed-version floors identified by the audit are
  aiohttp 3.14.3, authlib 1.6.12, click 8.3.3, cryptography 50.0.0, idna 3.15,
  langchain 1.3.9, langchain-anthropic 1.4.6, langchain-classic 1.0.7,
  langgraph-checkpoint 4.1.1, checkpoint-sqlite 3.1.1, langgraph-sdk 0.3.15,
  langsmith 0.8.18, lxml-html-clean 0.4.5, MCP 1.28.1, Pillow 12.3.0,
  pyasn1 0.6.4, pydantic-settings 2.14.2, PyJWT 2.13.0,
  python-multipart 0.0.31, and soupsieve 2.8.4.
- The project itself pins `pillow<12` using a stale comment. Current
  `podcast-creator 0.12.0` depends through `content-core 1.14.1`; that package
  accepts Pillow >=10.4 without an upper bound. A dry-run also confirms a
  bounded MCP `<2` solution.

## Required implementation

1. Update direct security floors conservatively in `pyproject.toml`; retain
   MCP `<2`, content-core `<2`, and existing Python/platform constraints.
2. Remove the stale Pillow blocker and require the audited fixed Pillow floor.
3. Regenerate `uv.lock`, then run `pip-audit` again and classify any remaining
   advisories honestly.
4. Update the frontend PostCSS override to the smallest fixed compatible
   version and regenerate `frontend/package-lock.json`; run production and full
   npm audits.
5. Resolve Knip's direct dependency hygiene without deleting intentional assets:
   remove confirmed unused `next-themes` and `@eslint/eslintrc`; add direct
   declarations for runtime/type/test imports (`katex`, PostCSS and the exact
   HAST/MDAST/unified/remark packages) only if `npm ls` and imports confirm them.
6. Run full backend hermetic tests, Ruff, product identity/rebrand audit,
   desktop tests, full frontend Vitest, lint, TypeScript, Next build, feature
   build contract, npm audit, pip-audit, and lockfile diff checks.

## Non-goals

- No application feature/refactor changes.
- No MCP 2.0 migration, LangChain 2.0 migration, or framework replacement.
- No source deletion based only on Knip; orphan cleanup is a separate task.

## 2026-08-11 worker receipt — Pillow resolver blocker

- Checkout advanced to `3c042a67` after the rebrand-only commit; preserved all
  listed untracked paths. A candidate `pyproject.toml` patch raises the
  supplied security floors, bounds MCP as `>=1.28.1,<2`, and removes the stale
  Pillow `<12` constraint; it remains uncommitted pending root reconciliation.
- Fresh `uv lock --dry-run` fails before writing `uv.lock`: the only available
  `podcast-creator==0.12.0` requires `moviepy>=2.2.1`, whose available
  solution requires `Pillow<12`, conflicting with the audited `Pillow>=12.3.0`.
  `uv` reports the project requirements are unsatisfiable for the win32 split;
  no compatible podcast-creator release is available in the resolver.
- Per the explicit resolver-conflict stop line, no lockfile/frontend edits or
  full release gates were run. Open decision: approve a separate
  podcast-creator/moviepy compatibility change, or retain the old Pillow floor
  and classify its advisories; do not widen this batch implicitly.

## 2026-08-11 final dependency-hardening receipt

- Applied the approved Python floors one-per-line, retained `mcp>=1.28.1,<2`,
  and kept `pillow>=11.3.0,<12.0` with a machine-readable exception comment:
  `podcast-creator 0.12.0 -> moviepy>=2.2.1 -> Pillow<12` prevents the
  audited Pillow 12.3.0 floor. Regenerated `uv.lock` (243 packages). Added
  direct `pip>=26.1.2`; resolver selected pip 26.2.1 and cleared its advisories.
- Final production `pip-audit` has 25 Pillow records only (Pillow 11.3.0):
  PYSEC-2026-165, 2249, 2250, 2251, 2252, 2253, 2254, 2255, 2256, 2257,
  2874, 3451, 3453, 3454, 3493, 3494, 3495, 3496. Available fixes are
  12.1.1/12.2.0/12.3.0, all incompatible with the upstream MoviePy bound.
- Frontend removed unused `next-themes` and `@eslint/eslintrc`; added confirmed
  direct imports/types (`katex`, HAST/MDAST, `remark-parse`, `unified`, PostCSS)
  and raised PostCSS to 8.5.26. npm production/full audits are zero; Knip has
  no dependency/devDependency/unlisted/unresolved findings (intentional 9
  orphan files and 145 exports remain outside this batch).
- Rebrand allowlist changed only the actual pyproject include anchor (line 95
  -> 105) and its exact coverage/pinned digests; docs/recreation/09 remains
  unchanged at its real line 102. Audit: compatibility_alias 825,
  historical_reference 1747, migration_documentation 584, unexpected 0,
  stale 0.
- Gates: backend 3964 passed/1 skipped/28 warnings; desktop exact two-path
  command 807 passed/2 skipped/5 warnings; frontend 202 files/1452 tests,
  lint, typecheck, Next build 23/23, and feature-build contract all passed;
  focused identity/import compatibility 289 passed; Ruff, lock and diff checks
  passed; import/bootstrap smoke passed.
- Open risk: revisit the Pillow exception when MoviePy/podcast-creator lifts
  `<12`; no source refactor or orphan deletion was performed.

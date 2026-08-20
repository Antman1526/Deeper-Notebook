# Roadmap

**Status: 2026-08-19 · desktop `0.8.108` · server/container `1.8.5`**

Why this file exists: an inventory on 2026-08-19 found no roadmap or backlog
anywhere in the repository — only retrospective per-feature plans under
`docs/superpowers/plans/`. Answering "what needs building?" required
reconstructing it from feature-flag defaults, CI config, and §4 of
`recreation/PROJECT-DEEP-DIVE.md`. For a project with 49 API routers and 5,754
tests, that reconstruction cost was the most consequential missing artifact.

Everything below is either measured or explicitly marked as a judgement call.
Where a number appears, it came from running something, and the command is
named so it can be re-run rather than trusted.

---

## 1. Decisions waiting on a human

These are not engineering problems. They are choices only the owner can make,
and each is currently costing something while it stays open.

### 1.1 Revoke the leaked Google API key — **urgent**

A live-format key (`AIza…`, 39 chars) sits in git history and has been public on
GitHub. Purging history does **not** un-leak it: forks and clones retain it, and
it may be indexed. Rotation is the only remediation. A `git-filter-repo`
redaction was staged and is described in the commit history, but it is hygiene,
not a fix.

`history.txt` — a SurrealDB dump carrying Fernet-encrypted credential blobs — is
in history for the same reason and was staged for the same purge.

### 1.2 Source visuals ship **disabled**, with no recorded reason

`source_visuals_enabled()` defaults to `False`. Behind that flag:

| Piece | Size |
|---|---|
| `deeper_notebook/database/migrations/46.surrealql` | `source_visual_cache` / `_claim` / `_operation` |
| `api/routers/source_visuals.py` | 3 endpoints |
| `frontend/.../source-gallery/` | 9 components |
| Visual proof matrix | 8 cells × 3 themes × 4 viewports |

A complete, heavily tested subsystem that no user sees by default. Either it is
not ready — in which case *why* belongs in writing — or it should be turned on.
Right now it is neither, which is the worst of the three.

`research_runs_enabled()` is also off, but it gates one `ArtifactRail` surface
rather than a subsystem; the main Guided Research workspace is live in the
notebook page.

### 1.3 Adopt a formatter — now unblocked, needs one reviewed sitting

§2.1 was the blocker and is fixed (v0.8.109). Adoption was then attempted end to
end on 2026-08-19 and **reverted deliberately** — not because it failed, but
because of *how* it was passing. Reaching a green audit took a migration,
several repair runs, re-approving 38 pins by ordinal, and collapsing 160
allowlist entries. Driving a security allowlist to quiet with successive ad-hoc
scripts is how you get a gate that passes without meaning anything.

The work is now understood and bounded. `ruff format` touches ~702 files, and
the fallout is exactly two known, legitimate categories:

* **~1,040 pins relocate automatically.** `make repair-rebrand-pins` handles
  these; no judgement needed.
* **~39 pins are genuinely re-split.** Ruff moves a trailing `)` onto its own
  line, so the approved text changes by punctuation while its meaning does not.
  Each needs re-approval. The mapping is unambiguous — for every affected
  (path, pattern) the live occurrence count equals the pinned count, so the
  k-th live occurrence is the k-th approval.
* **~160 entries collapse as duplicates.** Two IDENTICAL lines in one file now
  hash the same, because the key is content plus intra-line ordinal rather than
  position. One approval covering both is the intended behaviour; the allowlist
  is a mapping, so the duplicates must be removed rather than tolerated.

Do it as a reviewable diff in one sitting with the allowlist changes actually
read, not as a byproduct of chasing a green check. That is the whole remaining
cost, and it is a few hours of attention rather than an engineering problem.

---

## 2. Engineering work, ranked by payoff per unit of risk

### 2.1 Re-key the rebrand allowlist — **DONE in v0.8.109**

Approvals are pinned to `(path, pattern, source, line, column, sha256(RAW
line))`. Every positional component moves when a file is edited, so:

* an edit *above* an approved line invalidates a still-correct approval — this
  ratchet fired three separate times during one working session, once relocating
  **416 pins** for a single edit; and
* a repo-wide reformat invalidates approvals wholesale, after which
  `--regenerate` aborts rather than rebuilding.

**Shipped 2026-08-19 (v0.8.109), on the second attempt.** The digest now hashes
whitespace-normalized content with the **intra-line ordinal folded in**, so
position leaves the lookup key while the distinction it carried — which
occurrence on a line is approved — does not. Measured: a 702-file `ruff format`
now leaves 1,044 pins auto-relocated and 49 genuinely changed, versus
invalidating everything and refusing to regenerate. Adopting a formatter is now
a bounded 49-entry review.

`make repair-rebrand-pins` remains for ordinary line shifts.

The first attempt, and why it was reverted: Normalizing whitespace in the digest and
falling back to `(path, pattern, source, digest)` got `--check` passing and cut
reformat damage from *everything* to five entries. It was reverted because
dropping `column` is a real weakening, and the suite already proves it:
`test_exact_context_does_not_hide_distinct_same_line_active_occurrence` puts the
legacy token on one line **twice** — one occurrence approved, one not — and
asserts the unapproved one is still flagged.

So `column` carries intra-line occurrence identity. The correct fix replaces
absolute column with an **occurrence ordinal within the line** (1st vs 2nd match
of that pattern): stable under reindentation, still distinguishing the two.
That ordinal must be stored in the allowlist *and* computed scanner-side, and
`classify_match` currently receives only the key — not the source line — so it
cannot derive one. Threading it through changes `_occurrence_key`'s arity and
ripples across ~55 assertions in `tests/test_product_identity.py`.

Two traps for whoever does it, both hit during the attempt:

* The hashing is **duplicated** in `scripts/persisted_queue_inventory.py`, which
  `rebrand_audit` imports and therefore cannot import back. Normalizing only one
  side made 30 compatibility entries resolve to a null contract.
* `_PINNED_SELECTOR_INVENTORY_SHA256` and each contract's `coverage_sha256` are
  computed over the entry keys. Change a key and all of them go stale; an empty
  pinned inventory looks like success right up until nothing is classified.

**Payoff:** unblocks the formatter *and* ends the ratchet.

Until then, `make repair-rebrand-pins` performs the repair in the required order
(relocate pins by content digest → inventory digest → coverage digests →
regenerate). It only moves a pin when the file still contains a line matching
the recorded digest; anything whose content genuinely changed is reported for
review rather than silently re-approved.

### 2.2 Retire source-shape tests — lower priority than it looks

469 assertions across 88 files that grep exact source text. Long assumed to be
what blocks a formatter; **measured on 2026-08-19 to not be**. They remain
brittle in principle and worth replacing with behavioural assertions
opportunistically, but rewriting them buys far less than §2.1.

### 2.3 `act()` warnings — three clusters, do them per-cluster

~100 warnings, every test passing. Grouped in PROJECT-DEEP-DIVE §4.6a:
`GuidedTipsProvider` (16, a `MutationObserver` firing outside `act`), Radix
internals in `Tooltip`/`Popper`/`Presence` (20, third-party), and assorted
unawaited async state. No shared fix. Worth doing when already working in a
given area; not worth a dedicated 25-file sweep immediately after the suite was
made deterministic.

### 2.4 Open architecture questions

Neither urgent nor forced, listed in full under "Areas for Review" in
PROJECT-DEEP-DIVE: the five near-identical tool-binding blocks (§2.1 there), the
module-global pooled HTTP client (§2.3), whether ~92 `# nosec` SurrealQL sites
justify a typed query builder (§4.4), and what could now be deleted.

---

## 3. Product gaps

* **Model-config health covers chat and embedding only.** TTS/STT/tools defaults
  can still dangle silently. Deliberate — listing every slot trains people to
  ignore the panel — but revisit if a support question ever traces to one.
* **Auto-route degrades silently.** With no benchmark history it now falls back
  to the configured default rather than dying (v0.8.100). Whether the toggle
  should *say* "nothing to route between yet" is unresolved.
* **Cold start is ~47s** (down from ~106s after freeing disk). Now dominated by
  a 4.9 GB GGUF cold-mmap, i.e. filesystem-bound rather than code-bound. Keep
  the volume off ~90% full; there is little left to win in code.
* **`source_visuals_enabled()` is not a registered setting.** It reads
  `os.environ` directly rather than going through `resolve_env`, so it alone
  ignores the product's legacy-alias normalization. This looked like a one-line
  inconsistency and is not: the name is absent from `environment.SETTINGS`, so
  `resolve_env` cannot resolve it at all — routing it through anyway silently
  makes the flag unreadable (verified: four tests fail immediately). The real
  fix is to register the setting, which brings alias handling and deprecation
  policy with it. Small, real, and larger than it appears.

---

## 4. What is deliberately *not* on this list

* **TODO debt.** Two `TODO` occurrences repo-wide, both an FSM enum value
  (`AgentState.TODO`). For ~180k LOC that is unusual and worth preserving.
* **Reconciling the two version tracks.** `desktop/__init__.py` (app) and
  `pyproject.toml` (server/container) version different artifacts and are
  intentionally unreconciled. It confuses every reader; it is still correct.
* **`pillow < 12`.** ~24 CVEs, accepted because moviepy 2.2.1 — verified the
  latest release — still pins `pillow<12.0`. Genuinely unresolvable upstream;
  re-check when moviepy moves.

---

## Re-running the evidence

```bash
make security-scan                      # Bandit HIGH gate + pip-audit
uv run python scripts/rebrand_audit.py --check
uv run pytest tests/ desktop/tests/ -q
cd frontend && npx vitest run
```

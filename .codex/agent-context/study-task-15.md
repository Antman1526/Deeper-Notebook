# Study Workbench Task 15 context

## Scope

Implement safe native inspection and explicit publication of Anki `.apkg`
packages for a Study Plan. This task owns the archive/SQLite boundary and the
atomic native-card publication adapter. It does not own HTTP/UI/export, which
remain Task 16.

## Approved boundaries

- Use migration `44.surrealql` / `44_down.surrealql`; brief migration 43 is
  stale because Task 10 already owns migration 43.
- Preserve `StudyCard`, `StudyRepository`, `study_plan_card`, and native FSRS
  as the only card/scheduling authority. Imported schedules are compatibility
  metadata only and must not replace native scheduling state.
- Inspection is read-only. Import is preview then explicit publish; never
  publish merely because a file was selected or inspected.
- Validate all ZIP metadata before reading any member. Never call extract or
  extractall. Copy only the validated collection member to a task-owned temp
  file.
- Treat `.apkg` as untrusted. Reject traversal/absolute/duplicate/symlink
  members, unsafe or overlong names, member/count/size/ratio bombs, unknown
  collection variants, malformed media JSON, non-numeric media members,
  hostile templates/HTML/file references, unsupported schemas, and invalid or
  over-limit SQLite records.
- SQLite must use URI `mode=ro&immutable=1`, `PRAGMA query_only=ON`,
  `trusted_schema=OFF`, a progress handler, fixed allowlisted schema and
  projections, and bounded notes/cards/models/decks/media/text.
- Support bounded Basic, Basic+reverse, and Cloze translation. Never execute
  templates, JavaScript, add-ons, SQL supplied by the package, or read external
  paths.
- Native cards require bounded source/evidence citations. Use a local package
  evidence identity/hash; do not fabricate links to an existing Source record.
- Publication must atomically create/reuse exact native card snapshots,
  `study_plan_card` links, and a compatibility/import receipt. Request replay
  must compare the full canonical payload; mismatch conflicts safely.
- All errors are safe typed errors without paths, SQL, archive names beyond
  bounded display names, or provider/database internals.

## Required proof

- Strict RED before production.
- Security cases named in `.superpowers/sdd/task-15-brief.md`, including the
  published Anki untrusted-package local-file class.
- Focused import + scheduler + plan repository tests; Ruff; Bandit medium/high;
  compile/diff checks; migration symmetry; staged/range secret scans.
- Disposable real-Surreal proof for atomic publish, exact replay, mismatch
  conflict, and rollback on one invalid card.
- Separate commit: `feat(study): safely import Anki packages`.
- Preserve unrelated/untracked state and append durable milestones/results to
  this file and `/Users/Antman/.codex/context.md`.

## Real-Surreal integration proof — 2026-08-12

- Added `tests/integration/test_study_anki_import.py` against the existing
  disposable `clean_namespace` fixture. It proves real native-card,
  `study_plan_card`, and immutable compatibility-receipt rows for a valid
  reverse-card import; exact same-request replay; same-payload reuse under a
  new request ID; request/payload mismatch conflict with no mutation; malformed
  package, missing/wrong-table/archived-plan rejections with no mutation; and
  two independent same-payload publishers racing to one publication then
  converging by replay.
- Strict real-DB RED: 2 failed. Published `study_anki_import` arrays decode as
  lists, which strict receipt tuple fields rejected. The integration query also
  demonstrated that canonical Surreal RecordID text is
  `study_plan:⟨id⟩`, so persistence checks must use the repository's canonical
  plan representation rather than raw input text.
- Narrow runtime repair in `anki_repository.py`: convert only persisted
  `card_ids`, `deck_names`, `tags`, and `media_names` lists to tuples before
  strict `AnkiCompatibilityReceipt` validation. No publication, card, plan,
  scheduling, archive, or UI behavior changed. Root's deterministic card-token
  and canonical plan-ID changes were preserved.
- GREEN: `uv run ruff check tests/integration/test_study_anki_import.py` and
  `SURREAL_INTEGRATION=1 uv run pytest -q tests/integration/test_study_anki_import.py`
  both passed; 3 integration tests in 9.06s. No commit was created.

## Final implementation and review — 2026-08-12

- Root completed the safe inspector/repository/migration and local fixture
  builder after both Luna and approved Terra fallback produced no milestone.
- Final repairs bind one task-owned archive snapshot, fixed ZIP/SQLite/schema/
  scheduling/template/media bounds, full canonical payload, strict contract
  revalidation, and atomic approved-plan/active-unit/native-card/link/receipt
  authority. Imported schedule values remain inert; native FSRS is unchanged.
- GREEN: focused/adjacent 71 passed; real Surreal 3 passed; Ruff, compileall,
  Bandit medium/high, migration symmetry, and diff-check passed.
- Fresh Sol review APPROVED with no Critical/Important findings. OCR succeeded;
  Code Review Graph was unavailable. Task 16 owns HTTP/UI/export.

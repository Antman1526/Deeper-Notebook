# Task 7 correction report — 2026-07-27

- The read-only file-list contract now exposes the deterministic projection `note_id`; the file tree uses that returned ID verbatim for page navigation.
- Graph and link panes distinguish loading and failure from a truly empty result.
- All visible Knowledge Explorer strings use locale keys across shipped locale files; the empty-properties fallback is rendered when no properties exist.
- Verification: focused vault backend tests (55 passed, 21 skipped), Ruff, Task 7 frontend tests (26 passed), locale parity, frontend lint, production build, and `git diff --check`.

## Final-review corrections — 2026-07-27

- Local graph cache keys now include the selected center note while scan invalidation retains the vault-wide graph prefix, so navigation cannot reuse a prior center graph.
- Backlink responses project the resolved source note title as read-only display identity; backlink buttons preserve navigation by `source_note_id` and never expose absolute paths or source content.
- Client response validation rejects POSIX, drive-letter, and Windows UNC absolute paths (`\\server\\share` and `//server/share`).
- Verification: 56 focused backend vault API/repository tests, exact Task 7 frontend suite (17 tests), Ruff, frontend lint, production build, and `git diff --check`.

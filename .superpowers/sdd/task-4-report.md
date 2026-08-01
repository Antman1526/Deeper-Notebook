## 2026-08-01 — Task 4: Research Core Visual System, Responsive Rails, and Motion Safety

- Added the Research Core semantic deep-teal/cyan token family and responsive CSS hooks.
- Added labeled Sources and Intelligence drawers below 1024px, including explicit close controls and focus restoration to their triggers.
- Made the mode toolbar sticky below 720px with focus-safe scroll offsets and sequential surface layout.
- Added locale-complete drawer labels across all supported locale bundles.
- TDD evidence: the new visual-system and drawer interaction assertions first failed because the tokens, responsive hooks, and controls were absent; they pass after implementation.
- Verification passed: `(cd frontend && npx vitest run src/components/vault --pool=forks --maxWorkers=1 && npx tsc --noEmit)` — 32 files / 259 tests; TypeScript exited 0. Locale parity also passed: 13 checks across all 14 supported locales.
- Note: the broader locale test has one pre-existing unused-key failure for `knowledge.description`; it is unrelated to the new drawer labels, which are referenced by the Research Core shell.

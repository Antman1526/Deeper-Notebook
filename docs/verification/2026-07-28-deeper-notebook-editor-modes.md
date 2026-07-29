# Deeper Notebook editor modes and native vault proof

Date: 2026-07-28
Platform: macOS arm64
Branch: `codex/deeper-notebook-editor-modes`
Proof commit before this report: `c563590b0ac9da86716a42901c6fe192d4482689`

## Result

The packaged Deeper Notebook application completed the controlled, local-only
proof for the current read-only knowledge-editor slice. The proof used a
six-file synthetic fixture containing a mixed parent, Obsidian child, Logseq
child, and trust child. It did not mount, scan, or modify the user's Second
Brain.

The following behavior was demonstrated:

- Reader, Source, Live Preview, and Local Graph are available for canonical
  vault notes.
- Source and Live Preview remain read-only (`aria-readonly=true` and
  `contenteditable=false`).
- The selected note and Live Preview mode survive an application restart.
- Mixed vault registration creates the expected parent/child relationships.
- Child scans parse Obsidian, Logseq, and trust content independently.
- Repeated scans are idempotent.
- Trust import is idempotent and preserves its resolved state.
- Backlinks, outgoing links, local graph traversal, and note filtering return
  the expected synthetic-note relationships.
- The complete source-tree fingerprint is unchanged before and after all
  scans, imports, editor interactions, and restart.

## Implementation

The knowledge workspace stores an active canonical note tab and one of four
explicit editor modes. Reader and Live Preview render parsed content, Source
exposes the canonical source text without enabling mutation, and Local Graph
queries the bounded graph API around the selected note. Workspace state is
stored through the supported workspace endpoint and is restored when the
packaged runtime starts again.

The vault projection repository now treats source spans as the identity of a
parsed link edge. The parser intentionally includes an embed in both its
general link collection and its embed collection. Projection therefore adds a
synthetic embed edge only when that source span was not already represented.
This preserves one edge per source span and avoids a SurrealDB uniqueness
violation.

The native regression parses the complete Obsidian fixture, projects it twice,
expects `projected` followed by `unchanged`, verifies unique source spans, and
verifies that exactly two embed edges remain.

## Native runtime evidence

The packaged application started a persistent local API and its bundled
SurrealDB, reported ready with migrations applied, and was exercised through
both API and browser surfaces.

### Child mounts and scans

| Mount | Files after first scan | Third-scan delta | Final status |
| --- | ---: | ---: | --- |
| Mixed parent | 0 | 0 | ready-read-only |
| Obsidian child | 3 | 0 | ready-read-only |
| Logseq child | 1 | 0 | ready-read-only |
| Trust child | 1 | 0 | ready-read-only |

The parent excluded child content. Every child recorded the mixed parent as
`parent_vault_id`, and watch mode remained disabled.

### Trust import

- First import: 1 changed, 1 resolved, 0 unresolved.
- Second import: 0 changed, 1 unchanged, 1 resolved, 0 unresolved.
- Final summary: 1 total, 1 resolved, 0 unresolved.

### Links, graph, and search

- The synthetic Research note returned 4 blocks, 1 task, 2 outgoing
  relationships, and 4 backlinks.
- The bounded depth-2 graph contained Complete Research Note, Methods, and
  Research, with the expected wikilink, embed, tag, and backlink relationships.
- Filtering the Obsidian child by `Research` returned only Complete Research
  Note and Research.
- Browser inspection of Complete Research Note displayed backlinks, outgoing
  links, and all three local graph groups.

### Durability and source preservation

- Before proof: 6 files and manifest
  `d6a65aa2f1188744dcc6cf080a92f6a8760124f7b52c2440a4d3a2a2aec82649`.
- After restart: 6 files and the identical manifest.
- The active Complete Research Note tab and `live-preview` mode were restored.
- The restarted editor was still read-only.

## Verification commands and results

- Desktop package precondition: 642 passed, 2 skipped, 5 warnings.
- Backend package precondition: 3,192 passed, 1 skipped, 11 warnings.
- Focused vault parser/service suite: 205 passed, 1 warning.
- Native projection integration against bundled SurrealDB 2.1.0: 29 passed,
  7 warnings.
- Knowledge editor Playwright proof: 4 passed.
  - persists Live Preview without writing the vault;
  - records only the supported collection writes;
  - rejects off-namespace routes and wrong methods;
  - rejects unknown canonical descendants.
- Ruff passed for the modified repository and integration test.
- Next.js production build passed and included `/knowledge`.
- Rebrand audit: 0 unexpected active identities and 0 stale allowlist entries.
- `codesign --verify --deep --strict` passed for the application bundle.
- `hdiutil verify` passed for the DMG.

## Artifacts

- Application executable SHA-256:
  `f808470adb9183dfd0e86014184e9813437ae70e2378d25b0bc99ff5aa81ef27`
- DMG SHA-256:
  `82e9b4a29142b10a4faf18d94dc93b3e2be816265cd14c5e86a71bbb3f58f5af`

The build artifacts are local and intentionally not committed.

## Remaining gates

This proof does not claim complete Obsidian or Logseq parity.

1. The packaged launcher did not consistently exit its owned API and SurrealDB
   children after terminal signals. Exact owned PIDs were stopped after the
   proof, and no proof runtime remains active. Native shutdown cleanup is a
   release-hardening gate.
2. Native macOS menu Quit could not be tested because the Mac session was
   locked. It must be tested together with the shutdown fix.
3. A real Windows packaged launch and equivalent controlled proof remain
   required; no Windows runtime claim is made here.
4. Broader parity remains future work, including guarded write-back, Canvas,
   templates, plugin compatibility boundaries, and global graph workflows.
5. The first fixture location under `/tmp` was correctly rejected because
   macOS resolves `/tmp` through a symlink. The successful fixture used a
   descriptor-safe workspace path, demonstrating the fail-closed mount policy.

## 2026-07-29 packaged shutdown hardening update

The terminal-signal shutdown gate in item 1 above is resolved for the packaged
macOS arm64 runtime. The native AppKit event loop could remain blocked in
`NSApplication.run`, preventing Python's normal high-level signal handler from
running. The singleton now installs a POSIX wakeup-fd bridge so a dedicated
shutdown thread can immediately stop the supervisor, release the singleton,
flush logging, and exit even while the main thread remains inside Cocoa.

Verification used the exact rebuilt packaged executable for two complete
launch-to-ready-to-SIGTERM cycles:

- First launch: ready on API/frontend ports `63315`/`63316`; all 12 recorded
  launcher and descendant PIDs exited and both ports were released in 4
  seconds.
- Restart: ready on fresh API/frontend ports `63586`/`63587`; all 12 recorded
  launcher and descendant PIDs exited and both ports were released in 4
  seconds.
- Both launchers exited with status 143, logged
  `Received signal SIGTERM — cleaning runtime + exiting`, and released the
  singleton PID file.
- The final build preconditions passed: 645 desktop/memory tests with 2
  skipped, 3,192 backend tests with 1 skipped, and the Next.js production
  build including `/knowledge`.
- Focused singleton/launcher signal regressions passed: 3 tests.
- Rebrand audit, Ruff, `codesign --verify --deep --strict`, and `hdiutil
  verify` passed.

Updated local artifacts:

- Application executable SHA-256:
  `9e31e814d4d4dcf0acdbbfa83ec40488819832942957b88055a02aa086951136`
- DMG SHA-256:
  `ecb137b6164a61a6855dcf8e734349993d0e3a60d25271301aa586dfd7c77cca`

The remaining native release gates are macOS menu Quit from an unlocked
interactive session and the real Windows packaged launch/upgrade/repair/
uninstall proof. Broader Obsidian/Logseq parity work also remains as described
above.

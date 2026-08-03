# Deeper Notebook Command Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cross-vault quick switcher, knowledge-aware command palette,
safe slash commands, and explicit indexed/semantic search without enabling any
external-vault write.

**Architecture:** Extend the existing `cmdk` palette with a typed command
registry and two ephemeral Zustand stores: one carries the mounted Knowledge
page context, and one carries command-surface open requests. A pure catalog
module ranks mounted-vault file metadata and validates search provenance; React
hooks fetch per-vault catalogs and indexed results; focused UI components render
the quick switcher and palette while the durable knowledge workspace store
continues to own panes and tabs.

**Tech Stack:** Next.js 16, React 19, TypeScript, Zustand 5, TanStack Query 5,
cmdk, Zod 4, Vitest, Testing Library, Playwright.

## Global Constraints

- External vaults remain read-only.
- Do not add or call vault write, rename, move, delete, task-toggle, or raw-file
  endpoints.
- Resolve projected notes by `vault_id` and `note_id`; relative paths are
  display/provenance hints, never filesystem authorities.
- `Cmd/Ctrl+K` keeps all current global commands.
- `Cmd/Ctrl+O` opens the Knowledge quick switcher only while the Knowledge page
  is mounted.
- `/` opens safe Knowledge commands only when focus is inside the non-editable
  Knowledge workspace.
- Semantic search runs only after an explicit user action.
- Search results open a vault note only when canonical vault provenance passes
  validation.
- No automated test mounts or modifies the real Second Brain.
- Every source change follows red-green TDD and every task ends in a focused
  commit.

---

## File Map

### Pure command and catalog layer

- `frontend/src/lib/commands/knowledge-command-catalog.ts`
  - builds, normalizes, ranks, and maps projected note candidates;
  - validates indexed-search provenance before producing an open-tab request.
- `frontend/src/lib/commands/command-registry.ts`
  - defines command scope, safety, aliases, availability, and execution.
- `frontend/src/lib/commands/knowledge-command-context-store.ts`
  - holds only the currently mounted Knowledge page registration.
- `frontend/src/lib/commands/command-surface-store.ts`
  - carries monotonic requests to open the global, slash, or quick-switcher
    surface.

### Query layer

- `frontend/src/lib/hooks/use-knowledge-command-data.ts`
  - loads each ready mount's file catalog with `useQueries`;
  - exposes healthy results plus partial-failure state;
  - runs debounced text search and explicit semantic search.

### UI layer

- `frontend/src/components/vault/KnowledgeCommandBridge.tsx`
  - registers the page context and owns guarded `Cmd/Ctrl+O` and `/` listeners.
- `frontend/src/components/vault/KnowledgeQuickSwitcher.tsx`
  - renders ranked note results and opens the selected note in the focused pane.
- `frontend/src/components/common/CommandPalette.tsx`
  - preserves global commands and renders safe Knowledge commands and indexed
    results from the shared registry.
- `frontend/src/components/vault/KnowledgeExplorer.tsx`
  - supplies selected-vault, focus, scan, and workspace context to the bridge.

### Contracts and proof

- `frontend/src/lib/locales/*/index.ts`
  - adds complete command-navigation copy to all 14 locales.
- `frontend/src/lib/locales/index.test.ts`
  - enforces exact English copy and locale resolution.
- `frontend/e2e/fixtures/knowledge-editor-modes.ts`
  - adds a second vault note and search responses to the synthetic fixture.
- `frontend/e2e/knowledge-command-navigation.spec.ts`
  - proves keyboard navigation and absence of external writes.

---

### Task 1: Build the projected-note catalog and provenance gate

**Files:**
- Create: `frontend/src/lib/commands/knowledge-command-catalog.ts`
- Test: `frontend/src/lib/commands/knowledge-command-catalog.test.ts`

**Interfaces:**
- Consumes: `VaultFile`, `VaultMount`, `OpenKnowledgeTab`, `SearchResult`,
  `canonicalVaultRelativePathSchema`.
- Produces:
  - `KnowledgeCatalogCandidate`
  - `buildKnowledgeCatalog(mounts, filesByVault, openTabs)`
  - `rankKnowledgeCatalog(candidates, query, limit)`
  - `candidateToOpenTab(candidate)`
  - `searchResultToOpenTab(result)`

- [ ] **Step 1: Write failing catalog and provenance tests**

```ts
import { describe, expect, it } from 'vitest'

import type { OpenKnowledgeTab } from '@/lib/api/knowledge-workspace'
import type { VaultFile, VaultMount } from '@/lib/api/vault'
import type { SearchResult } from '@/lib/types/search'
import {
  buildKnowledgeCatalog,
  candidateToOpenTab,
  rankKnowledgeCatalog,
  searchResultToOpenTab,
} from './knowledge-command-catalog'

const mounts: VaultMount[] = [
  {
    id: 'vault:research',
    name: 'Research Core',
    format_mode: 'obsidian',
    state: 'ready-read-only',
    watch_enabled: false,
  },
]

const file = (noteId: string, relativePath: string): VaultFile => ({
  id: `vault_file:${noteId}`,
  note_id: noteId,
  vault_id: 'vault:research',
  relative_path: relativePath,
  file_kind: 'markdown',
  format: 'obsidian',
  content_hash: 'a'.repeat(64),
  parse_status: 'parsed',
  size_bytes: 10,
  modified_ns: 1,
  encoding: 'utf-8',
  newline: 'lf',
  deleted_state: 'present',
})

describe('knowledge command catalog', () => {
  it('ranks exact titles before prefixes, path matches, and vault matches', () => {
    const catalog = buildKnowledgeCatalog(
      mounts,
      new Map([
        ['vault:research', [
          file('note:exact', 'Research.md'),
          file('note:prefix', 'Research Methods.md'),
          file('note:path', 'research/Evidence.md'),
        ]],
      ]),
      [],
    )

    expect(rankKnowledgeCatalog(catalog, 'research', 10).map(item => item.noteId))
      .toEqual(['note:exact', 'note:prefix', 'note:path'])
  })

  it('folds case and diacritics and marks already-open notes', () => {
    const openTabs: OpenKnowledgeTab[] = [{
      vaultId: 'vault:research',
      noteId: 'note:cafe',
      title: 'Café',
      relativePath: 'Café.md',
    }]
    const catalog = buildKnowledgeCatalog(
      mounts,
      new Map([['vault:research', [file('note:cafe', 'Café.md')]]]),
      openTabs,
    )

    expect(rankKnowledgeCatalog(catalog, 'cafe', 10)[0]).toMatchObject({
      noteId: 'note:cafe',
      isOpen: true,
    })
  })

  it('maps a candidate to a canonical workspace tab request', () => {
    const [candidate] = buildKnowledgeCatalog(
      mounts,
      new Map([['vault:research', [file('note:plan', 'Plan.md')]]]),
      [],
    )

    expect(candidateToOpenTab(candidate)).toEqual({
      vaultId: 'vault:research',
      noteId: 'note:plan',
      title: 'Plan',
      relativePath: 'Plan.md',
    })
  })

  it('accepts only complete canonical search provenance', () => {
    const result = {
      id: 'note:plan',
      title: 'Plan',
      parent_id: 'vault:research',
      final_score: 1,
      created: '',
      updated: '',
      vault_provenance: {
        canonical_external: true,
        vault_id: 'vault:research',
        relative_path: 'Plan.md',
        source_hash: 'b'.repeat(64),
      },
    } satisfies SearchResult

    expect(searchResultToOpenTab(result)).toEqual({
      vaultId: 'vault:research',
      noteId: 'note:plan',
      title: 'Plan',
      relativePath: 'Plan.md',
    })
    expect(searchResultToOpenTab({
      ...result,
      vault_provenance: {
        ...result.vault_provenance,
        relative_path: '/Users/owner/Plan.md',
      },
    })).toBeNull()
    expect(searchResultToOpenTab({
      ...result,
      vault_provenance: {
        ...result.vault_provenance,
        source_hash: 'not-a-hash',
      },
    })).toBeNull()
  })
})
```

- [ ] **Step 2: Run the focused test and verify the red state**

Run:

```bash
cd frontend
npx vitest run src/lib/commands/knowledge-command-catalog.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: FAIL because `knowledge-command-catalog` does not exist.

- [ ] **Step 3: Implement the pure catalog**

```ts
import type { OpenKnowledgeTab } from '@/lib/api/knowledge-workspace'
import { canonicalVaultRelativePathSchema } from '@/lib/api/knowledge-workspace'
import type { VaultFile, VaultMount } from '@/lib/api/vault'
import type { SearchResult } from '@/lib/types/search'

export interface KnowledgeCatalogCandidate {
  key: string
  vaultId: string
  noteId: string
  vaultName: string
  format: VaultFile['format']
  title: string
  relativePath: string
  isOpen: boolean
}

function normalized(value: string): string {
  return value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase()
}

function titleFromPath(relativePath: string): string {
  return relativePath.split('/').at(-1)?.replace(/\.md$/iu, '') || relativePath
}

export function buildKnowledgeCatalog(
  mounts: VaultMount[],
  filesByVault: ReadonlyMap<string, readonly VaultFile[]>,
  openTabs: readonly OpenKnowledgeTab[],
): KnowledgeCatalogCandidate[] {
  const open = new Set(openTabs.map(tab => `${tab.vaultId}\0${tab.noteId}`))
  return mounts.flatMap(mount => (filesByVault.get(mount.id) || [])
    .filter(file => file.deleted_state === 'present' && file.parse_status === 'parsed')
    .map(file => ({
      key: `${file.vault_id}\0${file.note_id}`,
      vaultId: file.vault_id,
      noteId: file.note_id,
      vaultName: mount.name,
      format: file.format,
      title: titleFromPath(file.relative_path),
      relativePath: file.relative_path,
      isOpen: open.has(`${file.vault_id}\0${file.note_id}`),
    })))
    .sort((a, b) => a.key.localeCompare(b.key))
}

function score(candidate: KnowledgeCatalogCandidate, query: string): number {
  const title = normalized(candidate.title)
  const path = normalized(candidate.relativePath)
  const vault = normalized(candidate.vaultName)
  if (!query) return 10
  if (title === query) return 600
  if (title.startsWith(query)) return 500
  if (title.split(/\s+/u).some(token => token.startsWith(query))) return 400
  if (title.includes(query)) return 350
  if (path.split('/').some(segment => segment.startsWith(query))) return 300
  if (path.includes(query)) return 250
  if (vault.includes(query)) return 200
  return 0
}

export function rankKnowledgeCatalog(
  candidates: readonly KnowledgeCatalogCandidate[],
  query: string,
  limit: number,
): KnowledgeCatalogCandidate[] {
  const needle = normalized(query.trim())
  return candidates
    .map(candidate => ({ candidate, score: score(candidate, needle) }))
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score
      || a.candidate.title.localeCompare(b.candidate.title)
      || a.candidate.relativePath.localeCompare(b.candidate.relativePath)
      || a.candidate.key.localeCompare(b.candidate.key))
    .slice(0, Math.max(0, limit))
    .map(item => item.candidate)
}

export function candidateToOpenTab(
  candidate: KnowledgeCatalogCandidate,
): OpenKnowledgeTab {
  return {
    vaultId: candidate.vaultId,
    noteId: candidate.noteId,
    title: candidate.title,
    relativePath: candidate.relativePath,
  }
}

export function searchResultToOpenTab(
  result: SearchResult,
): OpenKnowledgeTab | null {
  const provenance = result.vault_provenance
  const relativePath = canonicalVaultRelativePathSchema.safeParse(
    provenance?.relative_path,
  )
  if (
    !provenance
    || provenance.canonical_external !== true
    || !provenance.vault_id
    || !result.id
    || !relativePath.success
    || !/^[0-9a-f]{64}$/iu.test(provenance.source_hash)
  ) return null
  return {
    vaultId: provenance.vault_id,
    noteId: result.id,
    title: result.title.trim() || titleFromPath(relativePath.data),
    relativePath: relativePath.data,
  }
}
```

- [ ] **Step 4: Run the focused test and verify green**

Run:

```bash
cd frontend
npx vitest run src/lib/commands/knowledge-command-catalog.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit the catalog**

```bash
git add \
  frontend/src/lib/commands/knowledge-command-catalog.ts \
  frontend/src/lib/commands/knowledge-command-catalog.test.ts
git commit -m "feat(knowledge): rank projected notes safely"
```

---

### Task 2: Add typed commands and generation-safe runtime stores

**Files:**
- Create: `frontend/src/lib/commands/command-registry.ts`
- Create: `frontend/src/lib/commands/command-registry.test.ts`
- Create: `frontend/src/lib/commands/knowledge-command-context-store.ts`
- Create: `frontend/src/lib/commands/knowledge-command-context-store.test.ts`
- Create: `frontend/src/lib/commands/command-surface-store.ts`
- Create: `frontend/src/lib/commands/command-surface-store.test.ts`

**Interfaces:**
- Consumes: workspace store actions and the approved safety rules.
- Produces:
  - `CommandScope`, `CommandSafety`, `CommandDefinition`
  - `knowledgeCommandDefinitions`
  - `availableKnowledgeCommands(context, mode)`
  - `executeKnowledgeCommand(id, context)`
  - `registerKnowledgeCommandContext(context)`
  - `clearKnowledgeCommandContext(generation)`
  - `requestCommandSurface(kind, initialQuery, invoker)`

- [ ] **Step 1: Write failing registry and store tests**

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  availableKnowledgeCommands,
  executeKnowledgeCommand,
  type KnowledgeCommandExecutionContext,
} from './command-registry'
import {
  clearKnowledgeCommandContext,
  registerKnowledgeCommandContext,
  resetKnowledgeCommandContextStore,
  useKnowledgeCommandContextStore,
} from './knowledge-command-context-store'
import {
  requestCommandSurface,
  resetCommandSurfaceStore,
  useCommandSurfaceStore,
} from './command-surface-store'

function context(): KnowledgeCommandExecutionContext {
  return {
    activePaneId: 'pane-1',
    activeTabId: 'tab-1',
    paneCount: 2,
    selectedVaultId: 'vault:one',
    setViewMode: vi.fn(),
    splitPane: vi.fn(),
    closePane: vi.fn(),
    closeTab: vi.fn(),
    scanSelectedVault: vi.fn(async () => undefined),
    focusFileTree: vi.fn(),
    focusActivePane: vi.fn(),
    focusLinks: vi.fn(),
    moveTab: vi.fn(),
  }
}

beforeEach(() => {
  resetKnowledgeCommandContextStore()
  resetCommandSurfaceStore()
})

describe('knowledge command registry', () => {
  it('exposes only read and workspace commands in slash mode', () => {
    const commands = availableKnowledgeCommands(context(), 'slash')
    expect(commands.length).toBeGreaterThan(0)
    expect(commands.every(command => command.safety !== 'external-write')).toBe(true)
  })

  it('disables close-pane with one pane and executes view changes exactly once', async () => {
    const singlePane = { ...context(), paneCount: 1 }
    expect(availableKnowledgeCommands(singlePane, 'global')
      .find(command => command.id === 'knowledge.close-pane')?.available).toBe(false)
    await expect(executeKnowledgeCommand(
      'knowledge.close-pane',
      singlePane,
    )).resolves.toBe(false)
    await expect(executeKnowledgeCommand(
      'knowledge.view-source',
      singlePane,
    )).resolves.toBe(true)
    expect(singlePane.setViewMode).toHaveBeenCalledWith('source')
  })
})

describe('knowledge command context registration', () => {
  it('does not let stale cleanup clear a newer registration', () => {
    const first = registerKnowledgeCommandContext({ selectedVaultId: 'vault:first' })
    const second = registerKnowledgeCommandContext({ selectedVaultId: 'vault:second' })
    clearKnowledgeCommandContext(first)
    expect(useKnowledgeCommandContextStore.getState().context?.selectedVaultId)
      .toBe('vault:second')
    clearKnowledgeCommandContext(second)
    expect(useKnowledgeCommandContextStore.getState().context).toBeNull()
  })
})

describe('command surface requests', () => {
  it('increments request identity and retains invocation focus', () => {
    const button = document.createElement('button')
    requestCommandSurface('slash', '/', button)
    expect(useCommandSurfaceStore.getState()).toMatchObject({
      requestId: 1,
      kind: 'slash',
      initialQuery: '/',
      invoker: button,
    })
  })
})
```

- [ ] **Step 2: Run the focused tests and verify red**

Run:

```bash
cd frontend
npx vitest run \
  src/lib/commands/command-registry.test.ts \
  src/lib/commands/knowledge-command-context-store.test.ts \
  src/lib/commands/command-surface-store.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: FAIL because all three modules are missing.

- [ ] **Step 3: Implement generation-safe stores**

```ts
import { create } from 'zustand'

export interface KnowledgeCommandPageContext {
  selectedVaultId: string | null
  fileTreeElement?: HTMLElement | null
  activePaneElement?: HTMLElement | null
  linksElement?: HTMLElement | null
  scanSelectedVault?: () => Promise<void>
}

interface KnowledgeCommandContextState {
  generation: number
  context: KnowledgeCommandPageContext | null
}

export const useKnowledgeCommandContextStore =
  create<KnowledgeCommandContextState>()(() => ({
    generation: 0,
    context: null,
  }))

export function registerKnowledgeCommandContext(
  context: KnowledgeCommandPageContext,
): number {
  const generation =
    useKnowledgeCommandContextStore.getState().generation + 1
  useKnowledgeCommandContextStore.setState({ generation, context })
  return generation
}

export function clearKnowledgeCommandContext(generation: number): void {
  if (useKnowledgeCommandContextStore.getState().generation !== generation) return
  useKnowledgeCommandContextStore.setState({ context: null })
}

export function resetKnowledgeCommandContextStore(): void {
  useKnowledgeCommandContextStore.setState({ generation: 0, context: null })
}
```

```ts
import { create } from 'zustand'

export type CommandSurfaceKind = 'global' | 'slash' | 'quick-switcher'

interface CommandSurfaceState {
  requestId: number
  kind: CommandSurfaceKind | null
  initialQuery: string
  invoker: HTMLElement | null
}

export const useCommandSurfaceStore = create<CommandSurfaceState>()(() => ({
  requestId: 0,
  kind: null,
  initialQuery: '',
  invoker: null,
}))

export function requestCommandSurface(
  kind: CommandSurfaceKind,
  initialQuery = '',
  invoker: HTMLElement | null = null,
): void {
  const requestId = useCommandSurfaceStore.getState().requestId + 1
  useCommandSurfaceStore.setState({ requestId, kind, initialQuery, invoker })
}

export function resetCommandSurfaceStore(): void {
  useCommandSurfaceStore.setState({
    requestId: 0,
    kind: null,
    initialQuery: '',
    invoker: null,
  })
}
```

- [ ] **Step 4: Implement the typed safe registry**

Use these exact command IDs:

```ts
export type KnowledgeCommandId =
  | 'knowledge.view-reading'
  | 'knowledge.view-source'
  | 'knowledge.view-live-preview'
  | 'knowledge.view-graph'
  | 'knowledge.split-right'
  | 'knowledge.split-down'
  | 'knowledge.close-pane'
  | 'knowledge.close-tab'
  | 'knowledge.previous-tab'
  | 'knowledge.next-tab'
  | 'knowledge.scan-vault'
  | 'knowledge.focus-files'
  | 'knowledge.focus-pane'
  | 'knowledge.focus-links'

export type CommandScope = 'global' | 'knowledge'
export type CommandSafety = 'read' | 'workspace' | 'external-write'
export type KnowledgeCommandMode = 'global' | 'slash'

export interface KnowledgeCommandExecutionContext {
  activePaneId: string | null
  activeTabId: string | null
  paneCount: number
  selectedVaultId: string | null
  setViewMode: (mode: 'reading' | 'source' | 'live-preview' | 'graph') => void
  splitPane: (direction: 'horizontal' | 'vertical') => void
  closePane: () => void
  closeTab: () => void
  scanSelectedVault: (() => Promise<void>) | null
  focusFileTree: (() => void) | null
  focusActivePane: (() => void) | null
  focusLinks: (() => void) | null
  moveTab: (offset: -1 | 1) => void
}

export interface CommandDefinition {
  id: KnowledgeCommandId
  scope: CommandScope
  safety: CommandSafety
  labelKey: string
  aliases: string[]
  keywords: string[]
  isAvailable: (context: KnowledgeCommandExecutionContext) => boolean
  unavailableReasonKey?: string
  execute: (context: KnowledgeCommandExecutionContext) => void | Promise<void>
}
```

Define all 14 commands above. The four view commands require an active tab;
split and focus-pane require an active pane; close-pane requires more than one
pane; close-tab and tab movement require an active tab; scan requires a selected
vault **and** a non-null scan callback; focus-file, focus-pane, and focus-links
require their corresponding non-null callbacks. All definitions must use only
`read` or `workspace` safety. Export:

```ts
export function availableKnowledgeCommands(
  context: KnowledgeCommandExecutionContext,
  mode: KnowledgeCommandMode,
): Array<Omit<CommandDefinition, 'isAvailable'> & { available: boolean }> {
  return knowledgeCommandDefinitions
    .filter(command => mode !== 'slash' || command.safety !== 'external-write')
    .map(({ isAvailable, ...command }) => ({
      ...command,
      available: isAvailable(context),
    }))
}

export function executeKnowledgeCommand(
  id: KnowledgeCommandId,
  context: KnowledgeCommandExecutionContext,
): Promise<boolean> {
  const command = knowledgeCommandDefinitions.find(candidate => candidate.id === id)
  if (
    !command
    || command.safety === 'external-write'
    || !command.isAvailable(context)
  ) {
    return Promise.resolve(false)
  }
  return Promise.resolve(command.execute(context)).then(() => true)
}
```

- [ ] **Step 5: Run the focused tests and verify green**

Run:

```bash
cd frontend
npx vitest run \
  src/lib/commands/command-registry.test.ts \
  src/lib/commands/knowledge-command-context-store.test.ts \
  src/lib/commands/command-surface-store.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: all registry and store tests pass.

- [ ] **Step 6: Commit the command contracts**

```bash
git add frontend/src/lib/commands
git commit -m "feat(knowledge): define safe command contracts"
```

---

### Task 3: Load cross-vault catalogs and explicit indexed search

**Files:**
- Create: `frontend/src/lib/hooks/use-knowledge-command-data.ts`
- Test: `frontend/src/lib/hooks/use-knowledge-command-data.test.tsx`

**Interfaces:**
- Consumes: `vaultApi.files`, `searchApi.search`, catalog builders, mounted vaults.
- Produces:
  - `useKnowledgeCatalog(mounts, openTabs, enabled)`
  - `useKnowledgeIndexedSearch(query, enabled)`
  - `runSemanticSearch(query)`

- [ ] **Step 1: Write failing catalog-query and search tests**

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { searchApi } from '@/lib/api/search'
import { vaultApi } from '@/lib/api/vault'
import {
  useKnowledgeCatalog,
  useKnowledgeIndexedSearch,
} from './use-knowledge-command-data'

vi.mock('@/lib/api/vault', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api/vault')>()
  return { ...actual, vaultApi: { ...actual.vaultApi, files: vi.fn() } }
})
vi.mock('@/lib/api/search', () => ({
  searchApi: { search: vi.fn() },
}))

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })}>
    {children}
  </QueryClientProvider>
)

describe('knowledge command data', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps healthy catalogs when one vault fails', async () => {
    vi.mocked(vaultApi.files)
      .mockResolvedValueOnce([{
        id: 'file:one',
        note_id: 'note:one',
        vault_id: 'vault:one',
        relative_path: 'One.md',
        file_kind: 'markdown',
        format: 'obsidian',
        content_hash: 'a'.repeat(64),
        parse_status: 'parsed',
        size_bytes: 1,
        modified_ns: 1,
        encoding: 'utf-8',
        newline: 'lf',
        deleted_state: 'present',
      }])
      .mockRejectedValueOnce(new Error('offline'))

    const { result } = renderHook(() => useKnowledgeCatalog([
      { id: 'vault:one', name: 'One', format_mode: 'obsidian',
        state: 'ready-read-only', watch_enabled: false },
      { id: 'vault:two', name: 'Two', format_mode: 'logseq',
        state: 'ready-read-only', watch_enabled: false },
    ], [], true), { wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.candidates.map(item => item.noteId)).toEqual(['note:one'])
    expect(result.current.failedVaultCount).toBe(1)
  })

  it('debounces text search and never starts vector search automatically', async () => {
    vi.useFakeTimers()
    vi.mocked(searchApi.search).mockResolvedValue({
      results: [],
      total_count: 0,
      search_type: 'text',
    })
    const { result, rerender } = renderHook(
      ({ query }) => useKnowledgeIndexedSearch(query, true),
      { initialProps: { query: 're' }, wrapper },
    )
    rerender({ query: 'research' })
    await vi.advanceTimersByTimeAsync(250)
    await waitFor(() => expect(result.current.text.isSuccess).toBe(true))
    expect(searchApi.search).toHaveBeenCalledTimes(1)
    expect(searchApi.search).toHaveBeenCalledWith(expect.objectContaining({
      query: 'research',
      type: 'text',
    }))
    expect(searchApi.search).not.toHaveBeenCalledWith(expect.objectContaining({
      type: 'vector',
    }))
    vi.useRealTimers()
  })

  it('starts vector search only through the explicit semantic action', async () => {
    vi.mocked(searchApi.search).mockResolvedValue({
      results: [],
      total_count: 0,
      search_type: 'vector',
    })
    const { result } = renderHook(
      () => useKnowledgeIndexedSearch('research', false),
      { wrapper },
    )

    result.current.runSemanticSearch()

    await waitFor(() => expect(result.current.semantic.isSuccess).toBe(true))
    expect(searchApi.search).toHaveBeenCalledTimes(1)
    expect(searchApi.search).toHaveBeenCalledWith(expect.objectContaining({
      query: 'research',
      type: 'vector',
    }))
  })
})
```

- [ ] **Step 2: Run the tests and verify red**

Run:

```bash
cd frontend
npx vitest run \
  src/lib/hooks/use-knowledge-command-data.test.tsx \
  src/lib/hooks/use-vault.test.tsx \
  --pool=forks --maxWorkers=1
```

Expected: FAIL because the new hook module is missing.

- [ ] **Step 3: Implement the catalog and search hooks**

```ts
import {
  useMutation,
  useQueries,
  useQuery,
} from '@tanstack/react-query'
import { useMemo } from 'react'
import { useDebounce } from 'use-debounce'

import type { OpenKnowledgeTab } from '@/lib/api/knowledge-workspace'
import { searchApi } from '@/lib/api/search'
import { vaultApi, type VaultMount } from '@/lib/api/vault'
import {
  buildKnowledgeCatalog,
  type KnowledgeCatalogCandidate,
} from '@/lib/commands/knowledge-command-catalog'
import { vaultKeys } from '@/lib/hooks/use-vault'

const searchRequest = (query: string, type: 'text' | 'vector') => ({
  query,
  type,
  limit: 25,
  search_sources: false,
  search_notes: true,
  minimum_score: 0.3,
})

export function useKnowledgeCatalog(
  mounts: VaultMount[],
  openTabs: readonly OpenKnowledgeTab[],
  enabled: boolean,
): {
  candidates: KnowledgeCatalogCandidate[]
  isLoading: boolean
  failedVaultCount: number
  retryFailedVaults: () => Promise<void>
} {
  const ready = mounts.filter(mount => mount.state === 'ready-read-only')
  const queries = useQueries({
    queries: ready.map(mount => ({
      queryKey: vaultKeys.files(mount.id),
      queryFn: () => vaultApi.files(mount.id),
      enabled,
      staleTime: 30_000,
    })),
  })
  const filesByVault = useMemo(() => new Map(
    ready.flatMap((mount, index) => queries[index]?.data
      ? [[mount.id, queries[index].data] as const]
      : []),
  ), [queries, ready])
  return {
    candidates: buildKnowledgeCatalog(ready, filesByVault, openTabs),
    isLoading: queries.some(query => query.isLoading),
    failedVaultCount: queries.filter(query => query.isError).length,
    retryFailedVaults: async () => {
      await Promise.all(
        queries.filter(query => query.isError).map(query => query.refetch()),
      )
    },
  }
}

export function useKnowledgeIndexedSearch(query: string, enabled: boolean) {
  const [debounced] = useDebounce(query.trim(), 250)
  const text = useQuery({
    queryKey: ['knowledge-command-search', 'text', debounced],
    queryFn: () => searchApi.search(searchRequest(debounced, 'text')),
    enabled: enabled && debounced.length >= 2,
    staleTime: 10_000,
  })
  const semantic = useMutation({
    mutationFn: (value: string) =>
      searchApi.search(searchRequest(value.trim(), 'vector')),
  })
  return {
    text,
    semantic,
    runSemanticSearch: () => {
      const value = query.trim()
      if (value.length >= 2) semantic.mutate(value)
    },
  }
}
```

If fake timers and `useDebounce` are nondeterministic in JSDOM, use real timers
with `waitFor` and assert that only the final query is sent. Do not replace
explicit vector invocation with automatic vector search.

- [ ] **Step 4: Run focused tests and verify green**

Run:

```bash
cd frontend
npx vitest run src/lib/hooks/use-knowledge-command-data.test.tsx \
  --pool=forks --maxWorkers=1
```

Expected: catalog, partial failure, debounced text-search, and explicit
semantic-search tests pass.

- [ ] **Step 5: Commit the query layer**

```bash
git add \
  frontend/src/lib/hooks/use-knowledge-command-data.ts \
  frontend/src/lib/hooks/use-knowledge-command-data.test.tsx
git commit -m "feat(knowledge): load command search data"
```

---

### Task 4: Add the quick switcher and guarded Knowledge bridge

**Files:**
- Create: `frontend/src/components/vault/KnowledgeQuickSwitcher.tsx`
- Test: `frontend/src/components/vault/KnowledgeQuickSwitcher.test.tsx`
- Create: `frontend/src/components/vault/KnowledgeCommandBridge.tsx`
- Test: `frontend/src/components/vault/KnowledgeCommandBridge.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.tsx`
- Modify: `frontend/src/components/vault/KnowledgeExplorer.test.tsx`

**Interfaces:**
- Consumes: command-surface requests, catalog hook, workspace store, current
  mounts, selected vault, focus elements, and scan mutation.
- Produces: `KnowledgeQuickSwitcher`, `KnowledgeCommandBridge`.

- [ ] **Step 1: Write failing keyboard and selection tests**

Cover these exact behaviors:

```tsx
it('opens Cmd+O, ranks notes, and opens the selected note in the active pane',
  async () => {
    renderKnowledgeExplorer()
    fireEvent.keyDown(document, { key: 'o', metaKey: true })
    const dialog = await screen.findByRole('dialog', {
      name: 'Quick switcher',
    })
    await userEvent.type(within(dialog).getByRole('combobox'), 'evidence')
    await userEvent.click(within(dialog).getByRole('option', {
      name: /Evidence/,
    }))
    const state = useKnowledgeWorkspaceStore.getState()
    expect(state.panes[state.activePaneId].tabs.at(-1)).toMatchObject({
      vaultId: 'vault:fixture',
      noteId: 'note:evidence',
    })
  })

it('opens slash commands only from the focused Knowledge workspace', () => {
  render(<KnowledgeCommandBridge {...props} />)
  fireEvent.keyDown(document.body, { key: '/' })
  expect(useCommandSurfaceStore.getState().kind).toBeNull()
  const workspace = screen.getByTestId('knowledge-workspace')
  workspace.focus()
  fireEvent.keyDown(workspace, { key: '/' })
  expect(useCommandSurfaceStore.getState()).toMatchObject({
    kind: 'slash',
    initialQuery: '/',
  })
})

it('does not intercept inputs, editable content, repeats, or composition', () => {
  render(<KnowledgeCommandBridge {...props} />)
  const input = screen.getByRole('textbox')
  for (const init of [
    { key: '/', target: input },
    { key: '/', isComposing: true },
    { key: '/', repeat: true },
  ]) {
    fireEvent.keyDown(init.target || screen.getByTestId('knowledge-workspace'), init)
  }
  expect(useCommandSurfaceStore.getState().kind).toBeNull()
})
```

Also assert that closing restores focus to the invoking element and that a
partial catalog failure renders `knowledge.partialCatalogFailure` without
hiding healthy results. Clicking the adjacent `common.retry` action must refetch
only failed catalogs.

- [ ] **Step 2: Run focused tests and verify red**

Run:

```bash
cd frontend
npx vitest run \
  src/components/vault/KnowledgeQuickSwitcher.test.tsx \
  src/components/vault/KnowledgeCommandBridge.test.tsx \
  src/components/vault/KnowledgeExplorer.test.tsx \
  --pool=forks --maxWorkers=1
```

Expected: the two new components are missing and Explorer has no bridge.

- [ ] **Step 3: Implement `KnowledgeCommandBridge`**

The bridge must:

```tsx
export interface KnowledgeCommandBridgeProps {
  workspaceRef: React.RefObject<HTMLElement | null>
  fileTreeRef: React.RefObject<HTMLElement | null>
  linksRef: React.RefObject<HTMLElement | null>
  selectedVaultId: string | null
  scanSelectedVault: () => Promise<void>
}
```

On mount, call `registerKnowledgeCommandContext` and return cleanup using the
captured generation. On context changes, register a new generation. Add one
capture-phase `keydown` listener that:

```ts
function isEditableTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (
    target.isContentEditable
    || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
  )
}

if (
  event.repeat
  || event.isComposing
  || isEditableTarget(event.target)
) return

if (event.key.toLowerCase() === 'o' && (event.metaKey || event.ctrlKey)) {
  event.preventDefault()
  event.stopPropagation()
  requestCommandSurface(
    'quick-switcher',
    '',
    document.activeElement instanceof HTMLElement ? document.activeElement : null,
  )
  return
}

if (
  event.key === '/'
  && !event.metaKey
  && !event.ctrlKey
  && !event.altKey
  && !event.shiftKey
  && workspaceRef.current?.contains(event.target as Node)
) {
  event.preventDefault()
  requestCommandSurface(
    'slash',
    '/',
    document.activeElement instanceof HTMLElement ? document.activeElement : null,
  )
}
```

- [ ] **Step 4: Implement `KnowledgeQuickSwitcher`**

Use the shared `CommandDialog` primitives. Subscribe to surface requests and
open only when `kind === 'quick-switcher'`. Build open tabs from:

```ts
const openTabs = Object.values(workspace.panes).flatMap(pane => pane.tabs)
```

Rank candidates with `rankKnowledgeCatalog(candidates, query, 50)`. Each item
value includes title, relative path, and vault name. On select:

```ts
openTab(candidateToOpenTab(candidate))
setOpen(false)
requestAnimationFrame(() => {
  if (invoker?.isConnected) invoker.focus()
})
```

Render:

- `knowledge.quickSwitcher` as the dialog title;
- `knowledge.quickSwitcherDescription` as its description;
- `knowledge.noMatchingFiles` for no exact candidates;
- `knowledge.partialCatalogFailure` with `{{count}}`;
- `common.retry` beside the partial-failure notice, wired to
  `retryFailedVaults`;
- a visible `knowledge.alreadyOpen` badge for open notes.

- [ ] **Step 5: Integrate the bridge without moving workspace ownership**

In `KnowledgeExplorer`:

- add refs for the root workspace, file tree aside, and links-inspector wrapper;
- add `data-testid="knowledge-workspace"` and `tabIndex={-1}` to the root;
- pass the existing selected vault and scan mutation to the bridge;
- render one `KnowledgeQuickSwitcher mounts={mounts.data || []}` sibling;
- do not change `openFile`, `navigate`, or durable persistence behavior.

Update Explorer tests to assert registration is cleared on unmount and
`scanSelectedVault` delegates only to the selected mount.

- [ ] **Step 6: Run focused tests and verify green**

Run:

```bash
cd frontend
npx vitest run \
  src/components/vault/KnowledgeQuickSwitcher.test.tsx \
  src/components/vault/KnowledgeCommandBridge.test.tsx \
  src/components/vault/KnowledgeExplorer.test.tsx \
  --pool=forks --maxWorkers=1
```

Expected: quick-switcher, keyboard-guard, focus-restoration, partial-failure,
registration-cleanup, and existing Explorer tests pass.

- [ ] **Step 7: Commit the quick switcher**

```bash
git add \
  frontend/src/components/vault/KnowledgeQuickSwitcher.tsx \
  frontend/src/components/vault/KnowledgeQuickSwitcher.test.tsx \
  frontend/src/components/vault/KnowledgeCommandBridge.tsx \
  frontend/src/components/vault/KnowledgeCommandBridge.test.tsx \
  frontend/src/components/vault/KnowledgeExplorer.tsx \
  frontend/src/components/vault/KnowledgeExplorer.test.tsx
git commit -m "feat(knowledge): add cross-vault quick switcher"
```

---

### Task 5: Refactor the global palette and add safe slash commands

**Files:**
- Modify: `frontend/src/components/common/CommandPalette.tsx`
- Create: `frontend/src/components/common/CommandPalette.test.tsx`
- Modify: `frontend/src/components/vault/KnowledgeWorkspaceLayout.tsx`
- Modify: `frontend/src/components/vault/KnowledgeWorkspaceLayout.test.tsx`

**Interfaces:**
- Consumes: typed registry, surface requests, runtime Knowledge context,
  workspace store, catalog/search hooks.
- Produces: one global palette supporting global and slash invocation.

- [ ] **Step 1: Write regression-first palette tests**

Mock the router, create dialogs, theme store, notebooks, vault APIs, and search
API. Prove existing behaviors before refactoring:

```tsx
it('preserves Cmd+K navigation, create, notebook, theme, Search, and Ask', async () => {
  renderPalette()
  fireEvent.keyDown(document, { key: 'k', metaKey: true })
  expect(await screen.findByRole('dialog', { name: 'Quick actions' }))
    .toBeVisible()
  expect(screen.getByRole('option', { name: 'Sources' })).toBeVisible()
  expect(screen.getByRole('option', { name: 'New notebook' })).toBeVisible()
  expect(screen.getByRole('option', { name: 'Dark' })).toBeVisible()
  expect(screen.getByRole('option', { name: 'Research Core' })).toBeVisible()
})

it('preserves Cmd+N, Cmd+U, and Cmd+/ global shortcuts', () => {
  renderPalette()
  fireEvent.keyDown(document, { key: 'n', metaKey: true })
  expect(openNotebookDialog).toHaveBeenCalledTimes(1)
  fireEvent.keyDown(document, { key: 'u', metaKey: true })
  expect(openSourceDialog).toHaveBeenCalledTimes(1)
  fireEvent.keyDown(document, { key: '/', metaKey: true })
  expect(router.push).toHaveBeenCalledWith('/search')
})

it('slash mode contains only safe knowledge commands', async () => {
  registerKnowledgeContextAndWorkspace()
  requestCommandSurface('slash', '/')
  expect(await screen.findByRole('option', { name: 'Source' })).toBeVisible()
  expect(screen.getByRole('option', { name: 'Split pane right' })).toBeVisible()
  expect(screen.queryByText(/delete|rename|move|toggle task/iu)).toBeNull()
})

it('executes commands against the focused pane and honors availability', async () => {
  replaceTwoPaneWorkspace()
  requestCommandSurface('slash', '/')
  await userEvent.click(await screen.findByRole('option', { name: 'Source' }))
  const state = useKnowledgeWorkspaceStore.getState()
  const pane = state.panes[state.activePaneId]
  expect(pane.tabs.find(tab => tab.id === pane.activeTabId)?.viewMode)
    .toBe('source')
})

it('shows text results and performs vector search only after selection', async () => {
  requestCommandSurface('global')
  await userEvent.type(await screen.findByRole('combobox'), 'research')
  expect(await screen.findByRole('option', { name: /Plan/ })).toBeVisible()
  expect(searchApi.search).toHaveBeenCalledWith(expect.objectContaining({
    type: 'text',
  }))
  expect(searchApi.search).not.toHaveBeenCalledWith(expect.objectContaining({
    type: 'vector',
  }))
  await userEvent.click(screen.getByRole('option', {
    name: 'Semantic search for research',
  }))
  expect(searchApi.search).toHaveBeenCalledWith(expect.objectContaining({
    type: 'vector',
  }))
})

it('does not guess a tab from invalid provenance', async () => {
  vi.mocked(searchApi.search).mockResolvedValue(searchResponseWithAbsolutePath)
  requestCommandSurface('global')
  await userEvent.type(await screen.findByRole('combobox'), 'research')
  expect(screen.queryByRole('option', { name: /Unsafe result/ })).toBeNull()
})
```

- [ ] **Step 2: Run the palette tests and verify the intended red state**

Run:

```bash
cd frontend
npx vitest run \
  src/components/common/CommandPalette.test.tsx \
  src/components/vault/KnowledgeWorkspaceLayout.test.tsx \
  --pool=forks --maxWorkers=1
```

Expected: existing global-regression assertions can be made green with the test
harness, while slash, registry execution, and indexed-result assertions fail.

- [ ] **Step 3: Expose pane focus targets without duplicating layout state**

Add optional callbacks to `KnowledgeWorkspaceLayoutProps`:

```ts
onPaneElement?: (paneId: string, element: HTMLElement | null) => void
```

Call it from `registerPane` alongside the existing internal pane registry. Add a
layout test proving the callback receives the focused pane element and receives
`null` on unmount. Do not store the element in the durable workspace document.

- [ ] **Step 4: Refactor palette open requests and preserve global shortcuts**

Keep the existing global keyboard guard and route/create/theme handlers. Replace
the local toggle-only lifecycle with:

```ts
const surface = useCommandSurfaceStore()

useEffect(() => {
  if (surface.requestId === 0 || surface.kind === 'quick-switcher') return
  setInvocationMode(surface.kind)
  setQuery(surface.initialQuery)
  setOpen(true)
}, [surface.requestId])
```

`Cmd/Ctrl+K` must call:

```ts
if (open) {
  setOpen(false)
} else {
  requestCommandSurface(
    'global',
    '',
    document.activeElement instanceof HTMLElement ? document.activeElement : null,
  )
}
```

On dialog close, clear query and restore focus to the connected invoker.
Add a regression assertion that pressing `Cmd/Ctrl+K` a second time closes the
open global palette.

- [ ] **Step 5: Build and execute Knowledge commands from live workspace state**

Construct `KnowledgeCommandExecutionContext` on every render from:

- `useKnowledgeWorkspaceStore`;
- the currently registered page context;
- active pane/tab IDs;
- the selected-vault scan callback;
- current focus elements.

`setViewMode`, `splitPane`, `closePane`, and `closeTab` must call existing store
actions with the current IDs. `moveTab(-1 | 1)` wraps within the active pane and
calls `activateTab`. Render `availableKnowledgeCommands` in a Knowledge group.
Disabled commands remain visible with their localized reason and cannot close
the palette. Await `executeKnowledgeCommand`; close only when it resolves
`true`. If it resolves `false` because live context became unavailable, keep the
palette open and announce `knowledge.commandUnavailable` through an
`aria-live="polite"` status element. If execution rejects, keep the palette open
and let the existing mutation error surface report the failure; do not convert a
failed scan into success.

Slash mode filters out global navigation, create, theme, notebook, Search/Ask,
and any future `external-write` command. Strip the leading `/` only for cmdk
filtering; preserve it in the visible input.

- [ ] **Step 6: Render exact, text, and explicit semantic results**

When invocation mode is global and Knowledge context exists:

- render up to 8 exact catalog candidates before indexed results;
- call `useKnowledgeIndexedSearch(query, open && query.trim().length >= 2)`;
- map only results accepted by `searchResultToOpenTab` into vault note items;
- omit any result that carries a `vault_provenance` object but fails canonical
  validation;
- route results with no vault provenance to
  `/search?q=${encodeURIComponent(query)}&mode=search`;
- render one force-mounted semantic action:

```tsx
<CommandItem
  value={`semantic ${query}`}
  onSelect={() => indexed.runSemanticSearch()}
>
  <Sparkles aria-hidden="true" />
  {t('knowledge.semanticSearchFor', { query })}
</CommandItem>
```

After vector results arrive, label their group
`knowledge.semanticSearchResults`. If the API returns the existing
embedding-model configuration error, render `knowledge.semanticUnavailable`
with a command that routes to `/settings/api-keys`.

Render semantic results only while
`indexed.semantic.variables === query.trim()`. This prevents a late response for
an older query from becoming selectable after the query changes. Never render
text or semantic result items while the dialog is closed.

- [ ] **Step 7: Run focused palette and layout tests**

Run:

```bash
cd frontend
npx vitest run \
  src/components/common/CommandPalette.test.tsx \
  src/components/vault/KnowledgeWorkspaceLayout.test.tsx \
  src/lib/commands/command-registry.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: global regression, slash safety, workspace execution, indexed search,
explicit vector search, provenance rejection, focus callback, and registry tests
pass.

- [ ] **Step 8: Commit the unified palette**

```bash
git add \
  frontend/src/components/common/CommandPalette.tsx \
  frontend/src/components/common/CommandPalette.test.tsx \
  frontend/src/components/vault/KnowledgeWorkspaceLayout.tsx \
  frontend/src/components/vault/KnowledgeWorkspaceLayout.test.tsx
git commit -m "feat(knowledge): unify palette and slash commands"
```

---

### Task 6: Complete localization and browser-level safety proof

**Files:**
- Modify: `frontend/src/lib/locales/en-US/index.ts`
- Modify: `frontend/src/lib/locales/bn-IN/index.ts`
- Modify: `frontend/src/lib/locales/ca-ES/index.ts`
- Modify: `frontend/src/lib/locales/de-DE/index.ts`
- Modify: `frontend/src/lib/locales/es-ES/index.ts`
- Modify: `frontend/src/lib/locales/fr-FR/index.ts`
- Modify: `frontend/src/lib/locales/it-IT/index.ts`
- Modify: `frontend/src/lib/locales/ja-JP/index.ts`
- Modify: `frontend/src/lib/locales/pl-PL/index.ts`
- Modify: `frontend/src/lib/locales/pt-BR/index.ts`
- Modify: `frontend/src/lib/locales/ru-RU/index.ts`
- Modify: `frontend/src/lib/locales/tr-TR/index.ts`
- Modify: `frontend/src/lib/locales/zh-CN/index.ts`
- Modify: `frontend/src/lib/locales/zh-TW/index.ts`
- Modify: `frontend/src/lib/locales/index.test.ts`
- Modify: `frontend/e2e/fixtures/knowledge-editor-modes.ts`
- Create: `frontend/e2e/knowledge-command-navigation.spec.ts`

**Interfaces:**
- Consumes: command-navigation UI and existing strict mocked API fixture.
- Produces: complete locale contract and browser proof with zero external writes.

- [ ] **Step 1: Add failing exact-copy and parity assertions**

Add:

```ts
const commandNavigationLocaleKeys = [
  'quickSwitcher',
  'quickSwitcherDescription',
  'alreadyOpen',
  'partialCatalogFailure',
  'knowledgeCommands',
  'semanticSearchFor',
  'semanticSearchResults',
  'semanticUnavailable',
  'previousTab',
  'nextTab',
  'closeActiveTab',
  'focusFiles',
  'focusPane',
  'focusLinks',
  'commandUnavailable',
] as const

it.each(Object.entries(resources))(
  '%s resolves every command-navigation key directly',
  (code, resource) => {
    for (const key of commandNavigationLocaleKeys) {
      const qualified = `knowledge.${key}`
      const value = getTranslation(
        resource.translation as Record<string, unknown>,
        qualified,
      )
      expect(value, `${code} is missing ${qualified}`).toEqual(expect.any(String))
      expect((value as string).trim()).not.toBe('')
    }
  },
)

it('keeps exact English command-navigation copy', () => {
  expect(enUS.knowledge).toMatchObject({
    quickSwitcher: 'Quick switcher',
    quickSwitcherDescription: 'Open an indexed vault note',
    alreadyOpen: 'Open',
    partialCatalogFailure: '{{count}} vault catalog could not be loaded',
    knowledgeCommands: 'Knowledge commands',
    semanticSearchFor: 'Semantic search for {{query}}',
    semanticSearchResults: 'Semantic results',
    semanticUnavailable: 'Semantic search requires an embedding model',
    previousTab: 'Previous tab',
    nextTab: 'Next tab',
    closeActiveTab: 'Close active tab',
    focusFiles: 'Focus vault files',
    focusPane: 'Focus active pane',
    focusLinks: 'Focus note links',
    commandUnavailable: 'Command unavailable',
  })
})
```

- [ ] **Step 2: Run the locale test and verify red**

Run:

```bash
cd frontend
npx vitest run src/lib/locales/index.test.ts --pool=forks --maxWorkers=1
```

Expected: all 15 new English keys are missing.

- [ ] **Step 3: Add exact localized command copy**

Add all 15 keys to every locale's existing `knowledge` object. Use the exact
English values above for `en-US`. Apply these exact values to the other locale
objects; do not substitute English fallbacks:

```ts
const approvedCommandNavigationCopy = {
  'bn-IN': {
    quickSwitcher: 'দ্রুত সুইচার',
    quickSwitcherDescription: 'সূচিবদ্ধ ভল্ট নোট খুলুন',
    alreadyOpen: 'খোলা',
    partialCatalogFailure: '{{count}}টি ভল্ট ক্যাটালগ লোড করা যায়নি',
    knowledgeCommands: 'জ্ঞান কমান্ড',
    semanticSearchFor: '{{query}}-এর জন্য অর্থভিত্তিক অনুসন্ধান',
    semanticSearchResults: 'অর্থভিত্তিক ফলাফল',
    semanticUnavailable: 'অর্থভিত্তিক অনুসন্ধানের জন্য এমবেডিং মডেল প্রয়োজন',
    previousTab: 'পূর্ববর্তী ট্যাব',
    nextTab: 'পরবর্তী ট্যাব',
    closeActiveTab: 'সক্রিয় ট্যাব বন্ধ করুন',
    focusFiles: 'ভল্ট ফাইলে ফোকাস করুন',
    focusPane: 'সক্রিয় পেনে ফোকাস করুন',
    focusLinks: 'নোট লিঙ্কে ফোকাস করুন',
    commandUnavailable: 'কমান্ড অনুপলব্ধ',
  },
  'ca-ES': {
    quickSwitcher: 'Selector ràpid',
    quickSwitcherDescription: 'Obre una nota indexada de la volta',
    alreadyOpen: 'Oberta',
    partialCatalogFailure: "No s'han pogut carregar {{count}} catàlegs de volta",
    knowledgeCommands: 'Ordres de coneixement',
    semanticSearchFor: 'Cerca semàntica de {{query}}',
    semanticSearchResults: 'Resultats semàntics',
    semanticUnavailable: "La cerca semàntica requereix un model d'incrustacions",
    previousTab: 'Pestanya anterior',
    nextTab: 'Pestanya següent',
    closeActiveTab: 'Tanca la pestanya activa',
    focusFiles: 'Enfoca els fitxers de la volta',
    focusPane: 'Enfoca el panell actiu',
    focusLinks: 'Enfoca els enllaços de la nota',
    commandUnavailable: 'Ordre no disponible',
  },
  'de-DE': {
    quickSwitcher: 'Schnellwechsler',
    quickSwitcherDescription: 'Indizierte Tresornotiz öffnen',
    alreadyOpen: 'Offen',
    partialCatalogFailure: '{{count}} Tresorkatalog konnte nicht geladen werden',
    knowledgeCommands: 'Wissensbefehle',
    semanticSearchFor: 'Semantische Suche nach {{query}}',
    semanticSearchResults: 'Semantische Ergebnisse',
    semanticUnavailable: 'Semantische Suche erfordert ein Einbettungsmodell',
    previousTab: 'Vorheriger Tab',
    nextTab: 'Nächster Tab',
    closeActiveTab: 'Aktiven Tab schließen',
    focusFiles: 'Tresordateien fokussieren',
    focusPane: 'Aktiven Bereich fokussieren',
    focusLinks: 'Notizlinks fokussieren',
    commandUnavailable: 'Befehl nicht verfügbar',
  },
  'es-ES': {
    quickSwitcher: 'Selector rápido',
    quickSwitcherDescription: 'Abrir una nota indexada de la bóveda',
    alreadyOpen: 'Abierta',
    partialCatalogFailure: 'No se pudieron cargar {{count}} catálogos de bóveda',
    knowledgeCommands: 'Comandos de conocimiento',
    semanticSearchFor: 'Búsqueda semántica de {{query}}',
    semanticSearchResults: 'Resultados semánticos',
    semanticUnavailable: 'La búsqueda semántica requiere un modelo de incrustaciones',
    previousTab: 'Pestaña anterior',
    nextTab: 'Pestaña siguiente',
    closeActiveTab: 'Cerrar pestaña activa',
    focusFiles: 'Enfocar archivos de la bóveda',
    focusPane: 'Enfocar panel activo',
    focusLinks: 'Enfocar enlaces de la nota',
    commandUnavailable: 'Comando no disponible',
  },
  'fr-FR': {
    quickSwitcher: 'Sélecteur rapide',
    quickSwitcherDescription: 'Ouvrir une note indexée du coffre',
    alreadyOpen: 'Ouverte',
    partialCatalogFailure: 'Impossible de charger {{count}} catalogues de coffre',
    knowledgeCommands: 'Commandes de connaissances',
    semanticSearchFor: 'Recherche sémantique de {{query}}',
    semanticSearchResults: 'Résultats sémantiques',
    semanticUnavailable: "La recherche sémantique nécessite un modèle d'embeddings",
    previousTab: 'Onglet précédent',
    nextTab: 'Onglet suivant',
    closeActiveTab: "Fermer l'onglet actif",
    focusFiles: 'Cibler les fichiers du coffre',
    focusPane: 'Cibler le volet actif',
    focusLinks: 'Cibler les liens de la note',
    commandUnavailable: 'Commande indisponible',
  },
  'it-IT': {
    quickSwitcher: 'Selettore rapido',
    quickSwitcherDescription: 'Apri una nota indicizzata della cassaforte',
    alreadyOpen: 'Aperta',
    partialCatalogFailure: 'Impossibile caricare {{count}} cataloghi della cassaforte',
    knowledgeCommands: 'Comandi della conoscenza',
    semanticSearchFor: 'Ricerca semantica per {{query}}',
    semanticSearchResults: 'Risultati semantici',
    semanticUnavailable: 'La ricerca semantica richiede un modello di embedding',
    previousTab: 'Scheda precedente',
    nextTab: 'Scheda successiva',
    closeActiveTab: 'Chiudi scheda attiva',
    focusFiles: 'Attiva i file della cassaforte',
    focusPane: 'Attiva il riquadro corrente',
    focusLinks: 'Attiva i link della nota',
    commandUnavailable: 'Comando non disponibile',
  },
  'ja-JP': {
    quickSwitcher: 'クイックスイッチャー',
    quickSwitcherDescription: 'インデックス済みの保管庫ノートを開く',
    alreadyOpen: '開いています',
    partialCatalogFailure: '{{count}} 件の保管庫カタログを読み込めませんでした',
    knowledgeCommands: 'ナレッジコマンド',
    semanticSearchFor: '{{query}} のセマンティック検索',
    semanticSearchResults: 'セマンティック結果',
    semanticUnavailable: 'セマンティック検索には埋め込みモデルが必要です',
    previousTab: '前のタブ',
    nextTab: '次のタブ',
    closeActiveTab: 'アクティブなタブを閉じる',
    focusFiles: '保管庫ファイルにフォーカス',
    focusPane: 'アクティブなペインにフォーカス',
    focusLinks: 'ノートリンクにフォーカス',
    commandUnavailable: 'コマンドを使用できません',
  },
  'pl-PL': {
    quickSwitcher: 'Szybki przełącznik',
    quickSwitcherDescription: 'Otwórz zindeksowaną notatkę skarbca',
    alreadyOpen: 'Otwarta',
    partialCatalogFailure: 'Nie udało się załadować {{count}} katalogów skarbca',
    knowledgeCommands: 'Polecenia wiedzy',
    semanticSearchFor: 'Wyszukiwanie semantyczne: {{query}}',
    semanticSearchResults: 'Wyniki semantyczne',
    semanticUnavailable: 'Wyszukiwanie semantyczne wymaga modelu osadzania',
    previousTab: 'Poprzednia karta',
    nextTab: 'Następna karta',
    closeActiveTab: 'Zamknij aktywną kartę',
    focusFiles: 'Ustaw fokus na plikach skarbca',
    focusPane: 'Ustaw fokus na aktywnym panelu',
    focusLinks: 'Ustaw fokus na linkach notatki',
    commandUnavailable: 'Polecenie niedostępne',
  },
  'pt-BR': {
    quickSwitcher: 'Alternador rápido',
    quickSwitcherDescription: 'Abrir uma nota indexada do cofre',
    alreadyOpen: 'Aberta',
    partialCatalogFailure: 'Não foi possível carregar {{count}} catálogos do cofre',
    knowledgeCommands: 'Comandos de conhecimento',
    semanticSearchFor: 'Pesquisa semântica por {{query}}',
    semanticSearchResults: 'Resultados semânticos',
    semanticUnavailable: 'A pesquisa semântica requer um modelo de embeddings',
    previousTab: 'Guia anterior',
    nextTab: 'Próxima guia',
    closeActiveTab: 'Fechar guia ativa',
    focusFiles: 'Focar arquivos do cofre',
    focusPane: 'Focar painel ativo',
    focusLinks: 'Focar links da nota',
    commandUnavailable: 'Comando indisponível',
  },
  'ru-RU': {
    quickSwitcher: 'Быстрый переключатель',
    quickSwitcherDescription: 'Открыть проиндексированную заметку хранилища',
    alreadyOpen: 'Открыта',
    partialCatalogFailure: 'Не удалось загрузить {{count}} каталогов хранилища',
    knowledgeCommands: 'Команды знаний',
    semanticSearchFor: 'Семантический поиск: {{query}}',
    semanticSearchResults: 'Семантические результаты',
    semanticUnavailable: 'Для семантического поиска нужна модель эмбеддингов',
    previousTab: 'Предыдущая вкладка',
    nextTab: 'Следующая вкладка',
    closeActiveTab: 'Закрыть активную вкладку',
    focusFiles: 'Перейти к файлам хранилища',
    focusPane: 'Перейти к активной панели',
    focusLinks: 'Перейти к ссылкам заметки',
    commandUnavailable: 'Команда недоступна',
  },
  'tr-TR': {
    quickSwitcher: 'Hızlı değiştirici',
    quickSwitcherDescription: 'Dizinlenmiş bir kasa notunu aç',
    alreadyOpen: 'Açık',
    partialCatalogFailure: '{{count}} kasa kataloğu yüklenemedi',
    knowledgeCommands: 'Bilgi komutları',
    semanticSearchFor: '{{query}} için anlamsal arama',
    semanticSearchResults: 'Anlamsal sonuçlar',
    semanticUnavailable: 'Anlamsal arama için bir gömme modeli gerekir',
    previousTab: 'Önceki sekme',
    nextTab: 'Sonraki sekme',
    closeActiveTab: 'Etkin sekmeyi kapat',
    focusFiles: 'Kasa dosyalarına odaklan',
    focusPane: 'Etkin bölmeye odaklan',
    focusLinks: 'Not bağlantılarına odaklan',
    commandUnavailable: 'Komut kullanılamıyor',
  },
  'zh-CN': {
    quickSwitcher: '快速切换',
    quickSwitcherDescription: '打开已索引的知识库笔记',
    alreadyOpen: '已打开',
    partialCatalogFailure: '无法加载 {{count}} 个知识库目录',
    knowledgeCommands: '知识命令',
    semanticSearchFor: '对 {{query}} 进行语义搜索',
    semanticSearchResults: '语义结果',
    semanticUnavailable: '语义搜索需要嵌入模型',
    previousTab: '上一个标签页',
    nextTab: '下一个标签页',
    closeActiveTab: '关闭当前标签页',
    focusFiles: '聚焦知识库文件',
    focusPane: '聚焦当前窗格',
    focusLinks: '聚焦笔记链接',
    commandUnavailable: '命令不可用',
  },
  'zh-TW': {
    quickSwitcher: '快速切換',
    quickSwitcherDescription: '開啟已索引的知識庫筆記',
    alreadyOpen: '已開啟',
    partialCatalogFailure: '無法載入 {{count}} 個知識庫目錄',
    knowledgeCommands: '知識命令',
    semanticSearchFor: '對 {{query}} 進行語意搜尋',
    semanticSearchResults: '語意結果',
    semanticUnavailable: '語意搜尋需要嵌入模型',
    previousTab: '上一個分頁',
    nextTab: '下一個分頁',
    closeActiveTab: '關閉目前分頁',
    focusFiles: '聚焦知識庫檔案',
    focusPane: '聚焦目前窗格',
    focusLinks: '聚焦筆記連結',
    commandUnavailable: '命令無法使用',
  },
} as const
```

Preserve `{{count}}` and `{{query}}` exactly. Verify with:

```bash
rg -n 'partialCatalogFailure:.*\\{\\{count\\}\\}' frontend/src/lib/locales/*/index.ts
rg -n 'semanticSearchFor:.*\\{\\{query\\}\\}' frontend/src/lib/locales/*/index.ts
```

Expected: 14 matches from each command.

- [ ] **Step 4: Extend the strict synthetic fixture**

Add `note:evidence` and `pages/evidence.md` to the fixture file list and page
routes. Add a POST `/api/search` handler that:

- accepts only `POST`;
- records the parsed request body in `state.searchRequests`;
- returns the Plan vault result with valid `vault_provenance`;
- returns status 400 with the existing embedding-model detail when
  `body.type === 'vector' && state.embeddingAvailable === false`.

Extend `KnowledgeFixtureState` with:

```ts
searchRequests: Array<Record<string, unknown>>
embeddingAvailable: boolean
```

No fixture route may allow a non-GET vault request except the existing explicit
scan endpoint.

- [ ] **Step 5: Write the browser proof**

```ts
test('quick switcher and slash commands preserve the external vault', async ({
  page,
}) => {
  const state = initialKnowledgeFixtureState()
  const vaultWrites: string[] = []
  const unexpectedApiTraffic: string[] = []
  await installKnowledgeShellMocks(page, unexpectedApiTraffic)
  await installKnowledgeRoutes(page, state, vaultWrites, unexpectedApiTraffic)
  await page.goto('/knowledge')

  await page.keyboard.press('Meta+o')
  const switcher = page.getByRole('dialog', { name: 'Quick switcher' })
  await expect(switcher).toBeVisible()
  await switcher.getByRole('combobox').fill('evidence')
  await switcher.getByRole('option', { name: /Evidence/ }).click()
  await expect(page.getByRole('tab', { name: 'Evidence' })).toHaveAttribute(
    'aria-selected',
    'true',
  )

  await page.getByTestId('knowledge-workspace').focus()
  await page.keyboard.press('/')
  const palette = page.getByRole('dialog', { name: 'Quick actions' })
  await expect(palette.getByRole('option', { name: 'Source' })).toBeVisible()
  await expect(palette.getByText(/delete|rename|move|toggle task/iu))
    .toHaveCount(0)
  await palette.getByRole('option', { name: 'Source' }).click()
  await expect(page.getByRole('button', { name: 'Source' }))
    .toHaveAttribute('aria-pressed', 'true')

  expect(vaultWrites).toEqual([])
  expect(unexpectedApiTraffic).toEqual([])
})

test('text and semantic search remain distinct and provenance-bound', async ({
  page,
}) => {
  const state = initialKnowledgeFixtureState()
  const vaultWrites: string[] = []
  const unexpectedApiTraffic: string[] = []
  await installKnowledgeShellMocks(page, unexpectedApiTraffic)
  await installKnowledgeRoutes(page, state, vaultWrites, unexpectedApiTraffic)
  await page.goto('/knowledge')

  await page.keyboard.press('Meta+k')
  await page.getByRole('combobox').fill('plan')
  await expect.poll(() => state.searchRequests.length).toBe(1)
  expect(state.searchRequests[0].type).toBe('text')
  await page.getByRole('option', { name: 'Semantic search for plan' }).click()
  await expect.poll(() => state.searchRequests.length).toBe(2)
  expect(state.searchRequests[1].type).toBe('vector')
  expect(vaultWrites).toEqual([])
  expect(unexpectedApiTraffic).toEqual([])
})
```

Use `Control+o` and `Control+k` on non-macOS projects by deriving the modifier
from `process.platform`; do not duplicate the test body.

- [ ] **Step 6: Run locale, component, and browser proof**

Run:

```bash
cd frontend
npx vitest run \
  src/lib/locales/index.test.ts \
  src/components/common/CommandPalette.test.tsx \
  src/components/vault/KnowledgeQuickSwitcher.test.tsx \
  src/components/vault/KnowledgeCommandBridge.test.tsx \
  --pool=forks --maxWorkers=1
npx playwright test e2e/knowledge-command-navigation.spec.ts \
  --project=mocked-browser
```

Expected: locale parity and command-navigation browser tests pass with zero
vault writes and zero unexpected API traffic.

- [ ] **Step 7: Commit localization and browser proof**

```bash
git add \
  frontend/src/lib/locales \
  frontend/e2e/fixtures/knowledge-editor-modes.ts \
  frontend/e2e/knowledge-command-navigation.spec.ts
git commit -m "test(knowledge): prove command navigation is read-only"
```

---

### Task 7: Run full regression, security, and production gates

**Files:**
- Modify only if a verification failure exposes a command-navigation defect.
- Update: `docs/verification/2026-07-29-deeper-notebook-command-navigation.md`

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: a durable verification record tied to the tested Git tree.

- [ ] **Step 1: Run the focused command-navigation suites**

```bash
cd frontend
npx vitest run \
  src/lib/commands/knowledge-command-catalog.test.ts \
  src/lib/commands/command-registry.test.ts \
  src/lib/commands/knowledge-command-context-store.test.ts \
  src/lib/commands/command-surface-store.test.ts \
  src/lib/hooks/use-knowledge-command-data.test.tsx \
  src/components/vault/KnowledgeQuickSwitcher.test.tsx \
  src/components/vault/KnowledgeCommandBridge.test.tsx \
  src/components/common/CommandPalette.test.tsx \
  src/components/vault/KnowledgeExplorer.test.tsx \
  src/components/vault/KnowledgeWorkspaceLayout.test.tsx \
  src/lib/locales/index.test.ts \
  --pool=forks --maxWorkers=1
```

Expected: all focused tests pass with zero failures.

- [ ] **Step 2: Run full frontend regression**

```bash
cd frontend
npm test
```

Expected: the complete Vitest suite passes with zero failures.

- [ ] **Step 3: Run lint and production build**

```bash
cd frontend
npm run lint
npm run build
```

Expected: ESLint exits 0 and Next.js produces a successful production build.

- [ ] **Step 4: Run the complete mocked browser suite**

```bash
cd frontend
npm run test:e2e:mocked
```

Expected: baseline, editor-mode, research-workbench, and command-navigation
specs pass.

- [ ] **Step 5: Run backend and repository safety regressions**

From the worktree root:

```bash
uv run pytest \
  tests/test_vault_api.py \
  tests/test_vault_repository.py \
  tests/test_knowledge_workspace_api.py \
  tests/test_knowledge_workspace_persistence.py \
  -q
uv run python scripts/rebrand_audit.py
cd frontend
npm audit --omit=dev
```

Expected:

- focused backend vault/workspace regressions pass;
- rebrand audit exits 0;
- production dependency audit reports zero vulnerabilities.

- [ ] **Step 6: Inspect the diff for accidental write paths**

```bash
git diff origin/main...HEAD -- \
  api deeper_notebook frontend/src frontend/e2e \
  | rg -n 'write|rename|move|delete|toggle|unlink|replace|PATCH|PUT|POST' \
  || true
rg -n \
  'vaultApi\\.(write|rename|move|delete|toggle)|/vaults/.*/(write|rename|move|delete|toggle)' \
  frontend/src frontend/e2e
```

Expected: matches are limited to the existing scan/search POSTs, test
assertions, labels, and unrelated pre-existing APIs. No new external-vault
mutation call exists.

- [ ] **Step 7: Write the verification record**

Create `docs/verification/2026-07-29-deeper-notebook-command-navigation.md`
with:

- branch and tested commit;
- exact commands and exit codes;
- focused and full test counts;
- browser proof results;
- production build result;
- external-write request count (`0`);
- unexpected API request count (`0`);
- production audit result;
- any non-blocking warnings, separated from pass claims.

- [ ] **Step 8: Commit the verification record**

```bash
git add docs/verification/2026-07-29-deeper-notebook-command-navigation.md
git commit -m "docs(verification): record command navigation proof"
```

- [ ] **Step 9: Fresh completion audit**

```bash
git status --short --branch
git log --oneline origin/main..HEAD
git diff --check origin/main...HEAD
```

Expected:

- clean worktree;
- the design, plan, feature, tests, localization, and verification commits are
  present;
- no whitespace errors.

Do not claim the full project goal complete. Completion of this plan advances
only the command-navigation slice; daily/unique notes, templates, bookmarks,
word count, advanced first-party features, and protected write-back remain.

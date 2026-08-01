import { useCallback, useEffect, useState } from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import { parseKnowledgeWorkspace, serializeKnowledgeWorkspace } from '@/lib/api/knowledge-workspace'
import {
  resetKnowledgeCommandContextStore,
  useKnowledgeCommandContextStore,
} from '@/lib/commands/knowledge-command-context-store'
import { resetCommandSurfaceStore } from '@/lib/commands/command-surface-store'

const states = vi.hoisted(() => ({
  page: { isLoading: false, isError: false },
  graph: { isLoading: false, isError: false },
  links: { isLoading: false, isError: false },
  hydration: { isLoading: false, isError: false },
  persistence: { isPending: false, isError: false, error: null as Error | null },
  persistenceWrites: vi.fn(),
}))
const vaultQueries = vi.hoisted(() => ({
  page: vi.fn(),
  backlinks: vi.fn(),
  outgoing: vi.fn(),
  scan: vi.fn(async (vaultId: string) => { void vaultId }),
}))
const vaultState = vi.hoisted(() => ({
  mounts: [{
    id: 'vault:one', name: 'Fixture', format_mode: 'markdown',
    state: 'ready-read-only', watch_enabled: true,
  }],
}))
const overlayQueries = vi.hoisted(() => ({
  notes: [] as Array<{
    id: string; source_authority: 'overlay'; space_id: string; projected_note_id: string; stable_id: string
    kind: 'daily' | 'unique'; date_key: string | null; relative_path: string; title: string; content_hash: string
    revision: number; projection_state: 'current'; encoding: 'utf-8'; newline: 'lf'; created_at: string; updated_at: string
  }>,
  today: vi.fn(),
  page: vi.fn(),
  pages: {} as Record<string, unknown>,
}))
const navigationQueries = vi.hoisted(() => ({
  bookmarks: { items: [] as unknown[], nextCursor: null },
  folders: { items: [] as unknown[] },
  workspaces: { items: [] as unknown[] },
  random: vi.fn(async () => ({ state: 'empty' as const, document: null })),
  create: vi.fn(async () => undefined),
  deleteBookmark: vi.fn(async () => undefined),
  updateBookmark: vi.fn(async () => undefined),
  deleteFolder: vi.fn(async () => undefined),
  restoreWorkspace: vi.fn<(...args: unknown[]) => Promise<unknown>>(async () => undefined),
  createWorkspace: vi.fn(async () => undefined),
  updateWorkspace: vi.fn(async () => undefined),
  duplicateWorkspace: vi.fn(async () => undefined),
  deleteWorkspace: vi.fn(async () => undefined),
}))
const pageIdentity = vi.hoisted(() => ({
  value: null as string | null,
}))
const searchView = vi.hoisted(() => ({
  calls: [] as Array<[string, boolean, { mode: string; spaceIds: string[]; authorityKinds: string[]; tags: string[] }]>,
  semanticRun: vi.fn(),
  results: [{ id: 'search:plan', title: 'Search plan' }],
}))

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: () => ({
    openSourceDialog: vi.fn(),
    openNotebookDialog: vi.fn(),
    openPodcastDialog: vi.fn(),
  }),
}))
vi.mock('@/lib/hooks/use-notebooks', () => ({
  useNotebooks: () => ({ data: [], isLoading: false }),
}))

const resolvedLink = {
  id: 'link:linked',
  source_note_id: 'note:one',
  target_note_id: 'note:linked',
  target_note_title: 'Linked canonical',
  target_relative_path: 'notes/linked.md',
  target_text: 'Linked mention',
  link_kind: 'wikilink',
  resolved: true,
  source_start: 0,
  source_end: 12,
}

const graphLink = {
  ...resolvedLink,
  id: 'link:graph-linked',
  target_note_id: 'note:graph-linked',
  target_note_title: 'Graph linked',
  target_relative_path: 'notes/graph-linked.md',
  target_text: 'Graph linked',
}

const files = [
  {
    id: 'vault_file:one',
    note_id: 'note:one',
    vault_id: 'vault:one',
    relative_path: 'notes/one.md',
    file_kind: 'markdown',
    format: 'markdown',
    content_hash: null,
    parse_status: 'parsed',
  },
  {
    id: 'vault_file:two',
    note_id: 'note:two',
    vault_id: 'vault:one',
    relative_path: 'notes/two.md',
    file_kind: 'markdown',
    format: 'markdown',
    content_hash: null,
    parse_status: 'parsed',
  },
] as const

function pageFor(noteId?: string) {
  const resolvedNoteId = noteId || 'note:one'
  const canonical = {
    'note:two': { title: 'Two', relativePath: 'notes/two.md' },
    'note:linked': {
      title: 'Linked canonical',
      relativePath: 'notes/linked.md',
    },
    'note:graph-linked': {
      title: 'Graph linked',
      relativePath: 'notes/graph-linked.md',
    },
    'note:archived': {
      title: 'Persisted one',
      relativePath: 'archive/persisted-one.md',
    },
  }[resolvedNoteId] ?? { title: 'One', relativePath: 'notes/one.md' }
  return {
    knowledge_document_id: pageIdentity.value,
    file: {
      id: `vault_file:${resolvedNoteId}`,
      note_id: resolvedNoteId,
      vault_id: 'vault:one',
      relative_path: canonical.relativePath,
      file_kind: 'markdown',
      format: 'markdown',
      content_hash: 'a'.repeat(64),
      parse_status: 'parsed',
      size_bytes: 5,
      modified_ns: 1,
      encoding: 'utf-8',
      newline: 'lf',
      deleted_state: 'present',
    },
    note: {
      id: resolvedNoteId,
      title: canonical.title,
      content: `# ${canonical.title}`,
      properties: {},
      tags: [],
    },
    blocks: [],
    tasks: [],
    outgoing_links: [resolvedLink],
    backlinks: [],
  }
}

function backlinkFor(noteId?: string) {
  const suffix = noteId === 'note:two' ? 'Two' : 'One'
  return [{
    id: `link:${suffix.toLowerCase()}`,
    source_note_id: `note:backlink-${suffix.toLowerCase()}`,
    target_note_id: noteId || 'note:one',
    target_text: suffix,
    source_note_title: `Backlink for ${suffix}`,
    link_kind: 'wikilink',
    resolved: true,
  }]
}

vi.mock('@/lib/hooks/use-vault', () => ({
  useVaults: () => ({
    data: vaultState.mounts,
    isLoading: false,
    isError: false,
  }),
  useVaultFiles: () => ({ data: files, isLoading: false, isError: false }),
  useVaultPage: (vaultId?: string, noteId?: string) => {
    vaultQueries.page(vaultId, noteId)
    return {
      data: noteId && !states.page.isLoading && !states.page.isError
        ? pageFor(noteId)
        : undefined,
      ...states.page,
    }
  },
  useVaultBacklinks: (vaultId?: string, noteId?: string) => {
    vaultQueries.backlinks(vaultId, noteId)
    return {
      data: noteId ? backlinkFor(noteId) : undefined,
      ...states.links,
    }
  },
  useVaultOutgoing: (vaultId?: string, noteId?: string) => (
    vaultQueries.outgoing(vaultId, noteId)
    || {
      data: noteId === 'note:one' ? [resolvedLink, graphLink] : [],
      ...states.links,
    }
  ),
  useVaultGraph: () => ({
    data: { nodes: [{ id: 'note:one', title: 'One' }], edges: [] },
    ...states.graph,
  }),
  useVaultCanvas: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
  useScanVault: (vaultId: string) => {
    const [isPending, setIsPending] = useState(false)
    const [error, setError] = useState<Error | null>(null)
    const mutateAsync = useCallback(async () => {
      setIsPending(true)
      setError(null)
      try {
        await vaultQueries.scan(vaultId)
      } catch (scanError) {
        const normalizedError = scanError instanceof Error
          ? scanError
          : new Error('scan failed')
        setError(normalizedError)
        throw normalizedError
      } finally {
        setIsPending(false)
      }
    }, [vaultId])
    return { mutateAsync, isPending, error }
  },
}))

vi.mock('@/lib/hooks/use-overlay', () => ({
  useOverlayNotes: () => ({ data: overlayQueries.notes, isLoading: false, isError: false }),
  useTodayOverlayNote: () => ({ mutateAsync: overlayQueries.today, isPending: false }),
  useCreateUniqueOverlayNote: () => ({ mutateAsync: vi.fn(), reset: vi.fn(), isPending: false, error: null }),
  useUpdateOverlayNote: () => ({ mutateAsync: vi.fn() }),
  useOverlayPage: (noteId?: string) => {
    overlayQueries.page(noteId)
    const data = noteId ? overlayQueries.pages[noteId] : undefined
    return {
      data,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn().mockResolvedValue({ data, isError: false, error: null }),
    }
  },
}))

vi.mock('@/lib/hooks/use-knowledge-workspace', () => ({
  useHydrateKnowledgeWorkspace: () => states.hydration,
  usePersistKnowledgeWorkspace: () => {
    useEffect(() => useKnowledgeWorkspaceStore.subscribe((state) => states.persistenceWrites(state)), [])
    return states.persistence
  },
}))

vi.mock('@/lib/hooks/use-knowledge-navigation', () => ({
  useKnowledgeBookmarks: () => ({ data: navigationQueries.bookmarks, isLoading: false, isError: false }),
  useKnowledgeFolders: () => ({ data: navigationQueries.folders, isLoading: false, isError: false }),
  useKnowledgeWorkspaces: () => ({ data: navigationQueries.workspaces, isLoading: false, isError: false }),
  useRandomKnowledgeNote: () => ({ mutateAsync: navigationQueries.random, isPending: false }),
  useCreateKnowledgeBookmark: () => ({ mutateAsync: navigationQueries.create }),
  useUpdateKnowledgeBookmark: () => ({ mutateAsync: navigationQueries.updateBookmark }),
  useDeleteKnowledgeBookmark: () => ({ mutateAsync: navigationQueries.deleteBookmark }),
  useDeleteKnowledgeFolder: () => ({ mutateAsync: navigationQueries.deleteFolder }),
  useRestoreKnowledgeWorkspace: () => ({ mutateAsync: navigationQueries.restoreWorkspace }),
  useCreateKnowledgeWorkspace: () => ({ mutateAsync: navigationQueries.createWorkspace }),
  useUpdateKnowledgeWorkspace: () => ({ mutateAsync: navigationQueries.updateWorkspace }),
  useDuplicateKnowledgeWorkspace: () => ({ mutateAsync: navigationQueries.duplicateWorkspace }),
  useDeleteKnowledgeWorkspace: () => ({ mutateAsync: navigationQueries.deleteWorkspace }),
}))

vi.mock('@/lib/hooks/use-knowledge-command-data', () => ({
  useKnowledgeCatalog: () => ({
    candidates: [],
    isLoading: false,
    failedVaultCount: 0,
    retryFailedVaults: vi.fn(async () => undefined),
  }),
  useKnowledgeIndexedSearch: (query: string, enabled: boolean, options: { mode: string; spaceIds: string[]; authorityKinds: string[]; tags: string[] }) => {
    searchView.calls.push([query, enabled, options])
    return {
    runSemanticSearch: searchView.semanticRun,
    text: { data: { results: searchView.results }, isCurrent: true },
    semantic: { data: undefined, variables: undefined, error: null },
  }},
}))

vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelsHealth: () => ({
    isLoading: false,
    isError: false,
    data: {
      overall: 'healthy',
      models: [{
        name: 'research-local', credential_id: 'credential:local', status: 'healthy',
        detail: null, latency_ms: 10, runtime: 'MLX', endpoint: null, probe_path: null,
      }],
    },
  }),
}))

vi.mock('./VaultGraph', () => ({
  VaultGraph: ({
    graph,
    onNavigate,
  }: {
    graph?: { nodes: Array<{ id: string }> }
    onNavigate: (noteId: string) => void
  }) => (
    <div>
      Local graph content
      <button type="button" onClick={() => onNavigate('note:graph-linked')}>
        Navigate graph node
      </button>
      {graph?.nodes.map((node) => (
        <button
          key={node.id}
          type="button"
          onClick={() => onNavigate(node.id)}
        >
          Navigate graph node {node.id}
        </button>
      ))}
    </div>
  ),
}))
vi.mock('./VaultLinks', () => ({
  VaultLinks: ({
    title,
    links,
    direction,
    onNavigate,
  }: {
    title: string
    links: Array<{
      source_note_title?: string | null
      source_note_id: string
      target_note_id?: string | null
      target_text: string
    }>
    direction: 'source' | 'target'
    onNavigate: (noteId: string) => void
  }) => (
    <section>
      <h2>{title}</h2>
      {links.map((link) => (
        <div key={`${direction}:${link.source_note_id}:${link.target_text}`}>
          <p>
            {direction === 'source'
              ? link.source_note_title || link.source_note_id
              : link.target_text}
          </p>
          <button
            type="button"
            onClick={() => onNavigate(
              direction === 'source'
                ? link.source_note_id
                : link.target_note_id!,
            )}
          >
            Navigate {direction} {link.target_text}
          </button>
        </div>
      ))}
    </section>
  ),
}))
vi.mock('./VaultMarkdown', () => ({
  VaultMarkdown: ({
    markdown,
    links,
    onNavigate,
  }: {
    markdown: string
    links: (typeof resolvedLink)[]
    onNavigate: (noteId: string) => void
  }) => (
    <div>
      {markdown}
      {links[0]?.target_note_id && links[0]?.target_relative_path && (
        <button
          type="button"
          onClick={() => onNavigate(links[0].target_note_id!)}
        >
          Navigate Markdown link
        </button>
      )}
    </div>
  ),
}))
vi.mock('./VaultDocumentView', () => ({
  VaultDocumentView: ({ page, onNavigate }: {
    page: ReturnType<typeof pageFor>
    onNavigate: (noteId: string) => void
  }) => (
    <div>
      {page.note.content}
      <span>No properties</span>
      {page.outgoing_links[0]?.target_note_id
        && page.outgoing_links[0]?.target_relative_path && (
        <button
          type="button"
          onClick={() => onNavigate(page.outgoing_links[0].target_note_id!)}
        >
          Navigate Markdown link
        </button>
      )}
    </div>
  ),
}))

import { KnowledgeExplorer } from './KnowledgeExplorer'
import { CommandPalette } from '../common/CommandPalette'

async function renderExplorer() {
  const result = render(<KnowledgeExplorer />)
  await waitFor(() => {
    expect(screen.getAllByRole('treeitem')).toHaveLength(2)
  })
  return result
}

async function selectFile(name: string) {
  fireEvent.click(screen.getByRole('treeitem', { name }))
  await waitFor(() => {
    expect(screen.getByRole('tab', {
      name: name.endsWith('one.md') ? /one/i : /two/i,
    })).toBeInTheDocument()
  })
}

function selectLocalGraph() {
  fireEvent.click(screen.getByRole('button', { name: 'knowledge.localGraph' }))
}

describe('KnowledgeExplorer durable workspace integration', () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollIntoView = vi.fn()
    states.page = { isLoading: false, isError: false }
    states.graph = { isLoading: false, isError: false }
    states.links = { isLoading: false, isError: false }
    states.hydration = { isLoading: false, isError: false }
    states.persistence = { isPending: false, isError: false, error: null }
    states.persistenceWrites.mockClear()
    vi.clearAllMocks()
    searchView.calls = []
    searchView.semanticRun.mockClear()
    vaultState.mounts = [{
      id: 'vault:one', name: 'Fixture', format_mode: 'markdown',
      state: 'ready-read-only', watch_enabled: true,
    }]
    overlayQueries.notes = []
    overlayQueries.pages = {}
    resetKnowledgeCommandContextStore()
    resetCommandSurfaceStore()
    vaultQueries.outgoing.mockImplementation((_vaultId, noteId) => (
      noteId === 'note:one'
        ? { data: [resolvedLink, graphLink], ...states.links }
        : { data: [], ...states.links }
    ))
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
  })

  it('opens two deduplicated file tabs in the active pane', async () => {
    await renderExplorer()

    await selectFile('notes/one.md')
    await selectFile('notes/two.md')
    fireEvent.click(screen.getByRole('treeitem', { name: 'notes/one.md' }))

    const pane = useKnowledgeWorkspaceStore.getState().panes['pane-1']
    expect(pane.tabs).toHaveLength(2)
    expect(pane.tabs.map((tab) => tab.relativePath)).toEqual([
      'notes/one.md',
      'notes/two.md',
    ])
    expect(pane.tabs.find((tab) => tab.id === pane.activeTabId)?.noteId)
      .toBe('note:one')
  })

  it('mounts the Research Core shell with one main landmark and opens a Search mode tab', async () => {
    await renderExplorer()
    await selectFile('notes/one.md')

    expect(screen.getByRole('banner', { name: 'Research Core workspace' })).toBeInTheDocument()
    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getByRole('complementary', { name: 'knowledge.intelligenceDrawer' })).toBeInTheDocument()
    const launcher = screen.getByRole('toolbar', { name: 'Research modes' })
    expect(screen.getByRole('tab', { name: 'Read: One' })).toBeInTheDocument()

    fireEvent.keyDown(launcher, { key: '4', altKey: true })

    const activePane = useKnowledgeWorkspaceStore.getState().panes['pane-1']
    expect(activePane.tabs.find((tab) => tab.id === activePane.activeTabId))
      .toMatchObject({ mode: 'search', target: { kind: 'search' } })
    expect(screen.getByRole('tab', { name: 'Search: Search' })).toBeInTheDocument()
  })

  it('exposes labeled utility and intelligence drawers that restore focus to their triggers', async () => {
    await renderExplorer()

    const openSources = screen.getByRole('button', { name: 'knowledge.openUtilityDrawer' })
    const openIntelligence = screen.getByRole('button', { name: 'knowledge.openIntelligenceDrawer' })
    expect(openSources).toHaveAttribute('aria-controls', 'research-core-utility-drawer')
    expect(openIntelligence).toHaveAttribute('aria-controls', 'research-core-intelligence-drawer')

    fireEvent.click(openSources)
    const utilityDrawer = screen.getByRole('complementary', { name: 'knowledge.utilityDrawer' })
    expect(utilityDrawer).toHaveAttribute('data-drawer-open', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'knowledge.closeUtilityDrawer' }))
    await waitFor(() => expect(openSources).toHaveFocus())

    fireEvent.click(openIntelligence)
    const intelligenceDrawer = screen.getByRole('complementary', { name: 'knowledge.intelligenceDrawer' })
    expect(intelligenceDrawer).toHaveAttribute('data-drawer-open', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'knowledge.closeIntelligenceDrawer' }))
    await waitFor(() => expect(openIntelligence).toHaveFocus())
  })

  it('keeps a narrow Sources drawer closable after its desktop rail is collapsed', async () => {
    const matchMedia = vi.mocked(window.matchMedia)
    const createMediaQuery = (query: string, matches: boolean) => ({
      matches,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }) as unknown as MediaQueryList
    matchMedia.mockImplementation((query) => createMediaQuery(
      query,
      query === '(max-width: 1023px)',
    ))

    try {
      render(<KnowledgeExplorer />)
      await waitFor(() => {
        expect(screen.getAllByRole('treeitem', { hidden: true })).toHaveLength(2)
      })

      const openSources = screen.getByRole('button', { name: 'knowledge.openUtilityDrawer' })
      fireEvent.click(openSources)
      fireEvent.click(screen.getByRole('button', { name: 'Collapse utility sidebar' }))

      const closeSources = screen.getByRole('button', { name: 'knowledge.closeUtilityDrawer' })
      fireEvent.click(closeSources)
      await waitFor(() => expect(openSources).toHaveFocus())
    } finally {
      matchMedia.mockImplementation((query) => createMediaQuery(query, false))
    }
  })

  it('activates the indexed search result surface without replacing the active document', async () => {
    await renderExplorer()
    await selectFile('notes/one.md')
    const activeBefore = useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId
    act(() => useKnowledgeWorkspaceStore.getState().setActiveSearchContext({
      query: 'plan', mode: 'text', spaceIds: ['knowledge_engine_space:research'],
      authorityKinds: ['external_read_only'], tags: ['plans'],
    }))

    expect(screen.getByRole('region', { name: 'Active knowledge search' })).toHaveTextContent('text: plan')
    expect(screen.getByRole('list', { name: 'Knowledge search results' })).toHaveTextContent('Search plan')
    expect(searchView.calls).toContainEqual(['plan', true, {
      mode: 'text', spaceIds: ['knowledge_engine_space:research'], authorityKinds: ['external_read_only'], tags: ['plans'],
    }])
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId).toBe(activeBefore)
  })

  it('reruns semantic search when its saved descriptor changes or returns from text mode', async () => {
    await renderExplorer()
    act(() => useKnowledgeWorkspaceStore.getState().setActiveSearchContext({
      query: 'plan', mode: 'semantic', spaceIds: ['knowledge_engine_space:research'], authorityKinds: [], tags: ['plans'],
    }))
    await waitFor(() => expect(searchView.semanticRun).toHaveBeenCalledTimes(1))
    act(() => useKnowledgeWorkspaceStore.getState().setActiveSearchContext({
      query: 'plan', mode: 'semantic', spaceIds: ['knowledge_engine_space:research'], authorityKinds: ['external_read_only'], tags: ['plans'],
    }))
    await waitFor(() => expect(searchView.semanticRun).toHaveBeenCalledTimes(2))
    act(() => useKnowledgeWorkspaceStore.getState().setActiveSearchContext({
      query: 'plan', mode: 'text', spaceIds: [], authorityKinds: [], tags: [],
    }))
    act(() => useKnowledgeWorkspaceStore.getState().setActiveSearchContext({
      query: 'plan', mode: 'semantic', spaceIds: ['knowledge_engine_space:research'], authorityKinds: [], tags: ['plans'],
    }))
    await waitFor(() => expect(searchView.semanticRun).toHaveBeenCalledTimes(3))
  })

  it('clears its command registration on unmount', async () => {
    const { unmount } = await renderExplorer()
    expect(useKnowledgeCommandContextStore.getState().context?.selectedVaultId)
      .toBe('vault:one')
    expect(useKnowledgeCommandContextStore.getState().context?.activePaneElement)
      .toBe(screen.getByRole('region', {
        name: /knowledge\.knowledgePane pane-1/,
      }))
    unmount()
    expect(useKnowledgeCommandContextStore.getState().context).toBeNull()
  })

  it('registers programmatically focusable file, pane, and links regions', async () => {
    await renderExplorer()
    const context = useKnowledgeCommandContextStore.getState().context

    expect(context?.fileTreeElement).toHaveAttribute('tabindex', '-1')
    expect(context?.activePaneElement).toHaveAttribute('tabindex')
    expect(context?.linksElement).toHaveAttribute('tabindex', '-1')
  })

  it('delegates scan commands only to the selected mount', async () => {
    await renderExplorer()
    await useKnowledgeCommandContextStore.getState().context?.scanSelectedVault?.()
    expect(vaultQueries.scan).toHaveBeenCalledWith('vault:one')
  })

  it('keeps its command generation stable through a pending selected-vault scan', async () => {
    let resolveScan: (() => void) | undefined
    vaultQueries.scan.mockImplementationOnce(() => new Promise<void>(resolve => {
      resolveScan = resolve
    }))
    await renderExplorer()
    const generation = useKnowledgeCommandContextStore.getState().generation
    const scan = useKnowledgeCommandContextStore.getState().context?.scanSelectedVault

    const pending = scan?.()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'knowledge.scan' })).toBeDisabled()
    })
    expect(useKnowledgeCommandContextStore.getState().generation).toBe(generation)

    resolveScan?.()
    await pending
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'knowledge.scan' })).not.toBeDisabled()
    })
    expect(useKnowledgeCommandContextStore.getState().generation).toBe(generation)
  })

  it('keeps the palette open and announces a localized error when a scan rejects', async () => {
    vaultQueries.scan.mockRejectedValueOnce(new Error('private backend detail'))
    render(
      <>
        <KnowledgeExplorer />
        <CommandPalette />
      </>,
    )
    await waitFor(() => expect(screen.getAllByRole('treeitem')).toHaveLength(2))
    fireEvent.keyDown(screen.getByTestId('knowledge-workspace'), { key: '/' })
    const palette = await screen.findByRole('dialog', { name: 'common.quickActions' })

    fireEvent.click(within(palette).getByRole('option', {
      name: 'knowledge.commands.scanVault',
    }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('knowledge.loadError'))
    expect(screen.getByRole('alert')).not.toHaveTextContent('private backend detail')
    expect(palette).toBeVisible()
  })

  it('runs the document-metrics command through the registered palette context', async () => {
    render(
      <>
        <KnowledgeExplorer />
        <CommandPalette />
      </>,
    )
    await waitFor(() => expect(screen.getAllByRole('treeitem')).toHaveLength(2))
    await selectFile('notes/one.md')
    act(() => useKnowledgeWorkspaceStore.getState().setNavigation({ metricsVisible: false }))

    const workspace = screen.getByTestId('knowledge-workspace')
    workspace.focus()
    fireEvent.keyDown(workspace, { key: '/' })
    const palette = await screen.findByRole('dialog', { name: 'common.quickActions' })
    fireEvent.click(within(palette).getByRole('option', {
      name: 'knowledge.commands.toggleMetrics',
    }))

    await waitFor(() => {
      expect(useKnowledgeWorkspaceStore.getState().navigation.metricsVisible).toBe(true)
    })
  })

  it('copies the active tab when splitting and opens later selections only in the active pane', async () => {
    await renderExplorer()
    await selectFile('notes/one.md')

    fireEvent.click(screen.getByRole('button', {
      name: 'knowledge.splitPaneRight',
    }))
    await selectFile('notes/two.md')

    const workspace = useKnowledgeWorkspaceStore.getState()
    expect(workspace.activePaneId).toBe('pane-3')
    expect(workspace.panes['pane-1'].tabs.map((tab) => tab.noteId))
      .toEqual(['note:one'])
    expect(workspace.panes['pane-3'].tabs.map((tab) => tab.noteId))
      .toEqual(['note:one', 'note:two'])
    expect(
      workspace.panes['pane-3'].tabs.find(
        (tab) => tab.id === workspace.panes['pane-3'].activeTabId,
      )?.noteId,
    ).toBe('note:two')
  })

  it('updates the links inspector when a different pane receives focus', async () => {
    await renderExplorer()
    await selectFile('notes/one.md')
    fireEvent.click(screen.getByRole('button', {
      name: 'knowledge.splitPaneRight',
    }))
    await selectFile('notes/two.md')

    expect(screen.getByText('Backlink for Two')).toBeInTheDocument()
    fireEvent.focus(screen.getByRole('region', {
      name: /knowledge\.knowledgePane pane-1/,
    }))

    await waitFor(() => {
      expect(screen.getByText('Backlink for One')).toBeInTheDocument()
    })
    expect(screen.queryByText('Backlink for Two')).not.toBeInTheDocument()
  })

  it('opens pane-local Markdown navigation in its originating split pane', async () => {
    await renderExplorer()
    await selectFile('notes/one.md')
    fireEvent.click(screen.getByRole('button', {
      name: 'knowledge.splitPaneRight',
    }))

    fireEvent.focus(screen.getByRole('region', {
      name: /knowledge\.knowledgePane pane-1/,
    }))
    const paneThree = screen.getByRole('region', {
      name: /knowledge\.knowledgePane pane-3/,
    })
    fireEvent.click(within(paneThree).getByRole('button', {
      name: 'Navigate Markdown link',
    }))

    const workspace = useKnowledgeWorkspaceStore.getState()
    expect(workspace.panes['pane-1'].tabs.map((tab) => tab.noteId))
      .toEqual(['note:one'])
    expect(workspace.panes['pane-3'].tabs.map((tab) => tab.noteId))
      .toEqual(['note:one', 'note:linked'])
    expect(
      workspace.panes['pane-3'].tabs.find(
        (tab) => tab.id === workspace.panes['pane-3'].activeTabId,
      )?.noteId,
    ).toBe('note:linked')
  })

  it('opens resolved links with their canonical target path', async () => {
    await renderExplorer()
    await selectFile('notes/one.md')

    fireEvent.click(screen.getByRole('button', {
      name: 'Navigate Markdown link',
    }))

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[1])
      .toMatchObject({
        noteId: 'note:linked',
        title: 'Linked canonical',
        relativePath: 'notes/linked.md',
      })
  })

  it('keeps a listed target file identity while using its canonical link title', async () => {
    vaultQueries.outgoing.mockReturnValue({
      data: [{
        ...resolvedLink,
        target_note_id: 'note:two',
        target_note_title: 'Canonical Two',
        target_relative_path: 'notes/two.md',
        target_text: 'Mention Two',
      }],
      isLoading: false,
      isError: false,
    })
    await renderExplorer()
    await selectFile('notes/one.md')

    fireEvent.click(screen.getByRole('button', {
      name: 'Navigate Markdown link',
    }))

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[1])
      .toMatchObject({
        noteId: 'note:two',
        title: 'Two',
        relativePath: 'notes/two.md',
      })
  })

  it('uses target text as the display fallback for an empty canonical listed title', async () => {
    vaultQueries.outgoing.mockReturnValue({
      data: [{
        ...resolvedLink,
        target_note_id: 'note:two',
        target_note_title: '',
        target_relative_path: 'notes/two.md',
        target_text: 'Mention Two',
      }],
      isLoading: false,
      isError: false,
    })
    await renderExplorer()
    await selectFile('notes/one.md')

    fireEvent.click(screen.getByRole('button', {
      name: 'Navigate Markdown link',
    }))

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[1])
      .toMatchObject({
        noteId: 'note:two',
        title: 'Two',
        relativePath: 'notes/two.md',
      })
  })

  it('opens inspector outgoing links with their canonical target fields', async () => {
    await renderExplorer()
    await selectFile('notes/one.md')

    fireEvent.click(screen.getByRole('button', {
      name: 'Navigate target Linked mention',
    }))

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[1])
      .toMatchObject({
        noteId: 'note:linked',
        title: 'Linked canonical',
        relativePath: 'notes/linked.md',
      })
  })

  it('refuses resolved navigation without a canonical target path', async () => {
    vaultQueries.outgoing.mockReturnValue({
      data: [{ ...resolvedLink, target_relative_path: null }],
      isLoading: false,
      isError: false,
    })
    await renderExplorer()
    await selectFile('notes/one.md')

    expect(screen.queryByRole('button', {
      name: 'Navigate Markdown link',
    })).not.toBeInTheDocument()
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs)
      .toHaveLength(1)
  })

  it('fails closed when inspector links do not provide a canonical path', async () => {
    vaultQueries.outgoing.mockReturnValue({
      data: [{ ...resolvedLink, target_relative_path: null }],
      isLoading: false,
      isError: false,
    })
    await renderExplorer()
    await selectFile('notes/one.md')

    fireEvent.click(screen.getByRole('button', {
      name: 'Navigate target Linked mention',
    }))
    fireEvent.click(screen.getByRole('button', {
      name: 'Navigate source One',
    }))

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs)
      .toHaveLength(1)
  })

  it('opens pane-local graph navigation in its originating split pane', async () => {
    await renderExplorer()
    await selectFile('notes/one.md')
    fireEvent.click(screen.getByRole('button', {
      name: 'knowledge.splitPaneRight',
    }))

    const paneThree = screen.getByRole('region', {
      name: /knowledge\.knowledgePane pane-3/,
    })
    const graphTab = within(paneThree).getByRole('button', {
      name: 'knowledge.localGraph',
    })
    fireEvent.click(graphTab)
    await waitFor(() => {
      expect(within(paneThree).getByText('Local graph content'))
        .toBeInTheDocument()
    })
    fireEvent.focus(screen.getByRole('region', {
      name: /knowledge\.knowledgePane pane-1/,
    }))
    fireEvent.click(within(paneThree).getByRole('button', {
      name: 'Navigate graph node',
    }))

    const workspace = useKnowledgeWorkspaceStore.getState()
    expect(workspace.panes['pane-1'].tabs.map((tab) => tab.noteId))
      .toEqual(['note:one'])
    expect(workspace.panes['pane-3'].tabs.map((tab) => tab.noteId))
      .toEqual(['note:one', 'note:graph-linked'])
    expect(
      workspace.panes['pane-3'].tabs.find(
        (tab) => tab.id === workspace.panes['pane-3'].activeTabId,
      )?.noteId,
    ).toBe('note:graph-linked')
  })

  it('loads a persisted tab missing from the file listing when its active ID is null', async () => {
    useKnowledgeWorkspaceStore.getState().replaceWorkspace(parseKnowledgeWorkspace(serializeKnowledgeWorkspace({
      version: 2,
      activePaneId: 'pane-1',
      nextId: 3,
      panes: {
        'pane-1': {
          id: 'pane-1',
          activeTabId: null,
          tabs: [{
            id: 'tab-2',
            vaultId: 'vault:one',
            noteId: 'note:archived',
            title: 'Persisted one',
            relativePath: 'archive/persisted-one.md',
            viewMode: 'reading',
            sourceAuthority: 'external-vault',
            knowledgeDocumentId: null,
            graphViewport: { x: 0, y: 0, zoom: 1 },
          }],
        },
      },
      layout: { type: 'pane', paneId: 'pane-1' },
      navigation: useKnowledgeWorkspaceStore.getState().navigation,
    })))

    await renderExplorer()

    expect(screen.getByRole('tab', { name: 'Read: Persisted one' }))
      .toBeInTheDocument()
    expect(screen.getByText('Backlink for One')).toBeInTheDocument()
    expect(vaultQueries.page).toHaveBeenCalledWith(
      'vault:one',
      'note:archived',
    )
    expect(vaultQueries.backlinks).toHaveBeenCalledWith(
      'vault:one',
      'note:archived',
    )
  })

  it('persists Reader and Local Graph modes independently on each active tab', async () => {
    await renderExplorer()
    await selectFile('notes/one.md')

    selectLocalGraph()
    await waitFor(() => {
      expect(screen.getByText('Local graph content')).toBeInTheDocument()
    })
    await selectFile('notes/two.md')

    const paneRegion = screen.getByRole('region', {
      name: /knowledge\.knowledgePane pane-1/,
    })
    expect(
      within(paneRegion).getByRole('button', { name: 'knowledge.reader' }),
    ).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(within(paneRegion).getByRole('tab', { name: /one/i }))

    await waitFor(() => {
      expect(
        within(paneRegion).getByRole('button', { name: 'knowledge.localGraph' }),
      ).toHaveAttribute('aria-pressed', 'true')
    })
    const workspace = useKnowledgeWorkspaceStore.getState()
    expect(workspace.panes['pane-1'].tabs.map((tab) => [
      tab.noteId,
      tab.viewMode,
    ])).toEqual([
      ['note:one', 'graph'],
      ['note:two', 'reading'],
    ])
  })

  it('keeps open tabs visible while durable hydration is loading', async () => {
    useKnowledgeWorkspaceStore.getState().openTab({
      vaultId: 'vault:one',
      noteId: 'note:one',
      title: 'one',
      relativePath: 'notes/one.md',
    })
    states.hydration = { isLoading: true, isError: false }

    await renderExplorer()

    expect(screen.getByText('knowledge.workspaceLoading')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /one/i })).toBeInTheDocument()
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs)
      .toHaveLength(1)
  })

  it('shows a durable-save failure without discarding local tabs', async () => {
    states.persistence = {
      isPending: false,
      isError: true,
      error: new Error('disk unavailable'),
    }
    await renderExplorer()
    await selectFile('notes/one.md')

    expect(screen.getByRole('alert')).toHaveTextContent(
      'knowledge.workspaceSaveError',
    )
    expect(screen.getByRole('tab', { name: /one/i })).toBeInTheDocument()
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs)
      .toHaveLength(1)
  })
})

describe('KnowledgeExplorer query states', () => {
  beforeEach(() => {
    states.page = { isLoading: false, isError: false }
    states.graph = { isLoading: false, isError: false }
    states.links = { isLoading: false, isError: false }
    states.hydration = { isLoading: false, isError: false }
    states.persistence = { isPending: false, isError: false, error: null }
    vi.clearAllMocks()
    vaultState.mounts = [{
      id: 'vault:one', name: 'Fixture', format_mode: 'markdown',
      state: 'ready-read-only', watch_enabled: true,
    }]
    overlayQueries.notes = []
    overlayQueries.pages = {}
    resetKnowledgeCommandContextStore()
    vaultQueries.outgoing.mockImplementation((_vaultId, noteId) => (
      noteId === 'note:one'
        ? { data: [resolvedLink, graphLink], ...states.links }
        : { data: [], ...states.links }
    ))
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
  })

  it('shows loading state for link and graph queries instead of empty panes', async () => {
    states.links = { isLoading: true, isError: false }
    states.graph = { isLoading: true, isError: false }
    await renderExplorer()
    await selectFile('notes/one.md')

    expect(screen.getByText('knowledge.linksLoading')).toBeInTheDocument()
    expect(screen.getByText('No properties')).toBeInTheDocument()
    selectLocalGraph()
    await waitFor(() => {
      expect(screen.getByText('knowledge.graphLoading')).toBeInTheDocument()
    })
  })

  it('shows the retained page-load error in the active pane', async () => {
    states.page = { isLoading: false, isError: true }
    await renderExplorer()
    await selectFile('notes/one.md')

    expect(screen.getByRole('alert')).toHaveTextContent(
      'knowledge.loadError',
    )
  })

  it('shows errors for link and graph queries instead of empty panes', async () => {
    states.links = { isLoading: false, isError: true }
    states.graph = { isLoading: false, isError: true }
    await renderExplorer()
    await selectFile('notes/one.md')

    expect(screen.getByText('knowledge.linksLoadError')).toBeInTheDocument()
    selectLocalGraph()
    await waitFor(() => {
      expect(screen.getByText('knowledge.graphLoadError')).toBeInTheDocument()
    })
  })
})

describe('KnowledgeExplorer overlay authority', () => {
  beforeEach(() => {
    states.hydration = { isLoading: false, isError: false }
    states.persistence = { isPending: false, isError: false, error: null }
    vaultState.mounts = [{
      id: 'vault:one', name: 'Fixture', format_mode: 'markdown',
      state: 'ready-read-only', watch_enabled: true,
    }]
    overlayQueries.notes = []
    overlayQueries.pages = {}
    overlayQueries.today.mockReset()
    vi.clearAllMocks()
    resetKnowledgeCommandContextStore()
    resetCommandSurfaceStore()
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
  })

  it('renders the app-owned overlay even with no external mounts', async () => {
    vaultState.mounts = []
    render(<KnowledgeExplorer />)

    expect(await screen.findByRole('heading', { name: 'knowledge.overlay.name' })).toBeInTheDocument()
    expect(screen.getByText('knowledge.overlay.writable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'knowledge.scan' })).toBeNull()
  })

  it('never renders or executes an external scan while the overlay root is selected', async () => {
    overlayQueries.today.mockResolvedValue({
      overlay: {
        id: 'overlay_note:daily', source_authority: 'overlay', space_id: 'overlay_space:default',
        projected_note_id: 'projected:daily', stable_id: 'a'.repeat(20), kind: 'daily', date_key: '2026-07-29',
        relative_path: 'Daily/2026-07-29.md', title: '2026-07-29', content_hash: 'a'.repeat(64), revision: 1,
        projection_state: 'current', encoding: 'utf-8', newline: 'lf',
        created_at: '2026-07-29T00:00:00.000Z', updated_at: '2026-07-29T00:00:00.000Z',
      },
      editable_markdown: '# 2026-07-29\n',
      note: { id: 'projected:daily', title: '2026-07-29', content: '', properties: {}, tags: [] },
      blocks: [], tasks: [], outgoing_links: [], backlinks: [], graph: null,
    })
    render(<KnowledgeExplorer />)
    fireEvent.change(screen.getByLabelText('knowledge.mounts'), {
      target: { value: 'overlay:overlay_space:default' },
    })

    expect(screen.queryByRole('button', { name: 'knowledge.scan' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'knowledge.overlay.today' }))
    await waitFor(() => expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs.at(-1))
      .toMatchObject({ sourceAuthority: 'overlay', noteId: 'overlay_note:daily' }))
    expect(vaultQueries.scan).not.toHaveBeenCalled()
  })

  it('opens listed overlay notes with overlay authority', async () => {
    overlayQueries.notes = [{
      id: 'overlay_note:unique', source_authority: 'overlay', space_id: 'overlay_space:default',
      projected_note_id: 'projected:unique', stable_id: 'a'.repeat(20), kind: 'unique', date_key: null,
      relative_path: 'Notes/Research.md', title: 'Research', content_hash: 'a'.repeat(64), revision: 1,
      projection_state: 'current', encoding: 'utf-8', newline: 'lf',
      created_at: '2026-07-29T00:00:00.000Z', updated_at: '2026-07-29T00:00:00.000Z',
    }]
    render(<KnowledgeExplorer />)
    fireEvent.click(await screen.findByRole('button', { name: 'Research' }))

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs.at(-1))
      .toMatchObject({ sourceAuthority: 'overlay', vaultId: 'overlay_space:default' })
  })

  it('reuses overlay-authority link targets without enabling external vault paths', async () => {
    const source = {
      id: 'overlay_note:source',
      source_authority: 'overlay' as const,
      space_id: 'overlay_space:default',
      projected_note_id: 'note:source',
      stable_id: 'stable-overlay-source',
      kind: 'unique' as const,
      date_key: null,
      relative_path: 'Notes/20260729-1542 Overlay Source.md',
      title: 'Overlay Source',
      content_hash: 'a'.repeat(64),
      revision: 1,
      projection_state: 'current' as const,
      encoding: 'utf-8' as const,
      newline: 'lf' as const,
      created_at: '2026-07-29T00:00:00.000Z',
      updated_at: '2026-07-29T00:00:00.000Z',
    }
    const target = {
      ...source,
      id: 'overlay_note:target',
      projected_note_id: 'note:target',
      stable_id: 'stable-overlay-target',
      relative_path: 'Notes/20260729-1543 Overlay Target.md',
      title: 'Overlay Target',
      content_hash: 'b'.repeat(64),
    }
    const outgoing = {
      ...resolvedLink,
      source_note_id: source.projected_note_id,
      source_overlay_note_id: source.id,
      source_relative_path: source.relative_path,
      target_note_id: target.projected_note_id,
      target_overlay_note_id: target.id,
      target_note_title: target.title,
      target_relative_path: target.relative_path,
      target_text: 'Overlay mention',
    }
    overlayQueries.notes = [source, target]
    overlayQueries.pages = {
      [source.id]: {
        overlay: source,
        editable_markdown: '# Source\n',
        note: {
          id: source.projected_note_id,
          title: source.title,
          markdown: '# Source\n',
          properties: {},
          tags: [],
        },
        blocks: [],
        tasks: [],
        outgoing_links: [outgoing],
        backlinks: [],
        graph: null,
      },
      [target.id]: {
        overlay: target,
        editable_markdown: '# Target\n',
        note: {
          id: target.projected_note_id,
          title: target.title,
          markdown: '# Target\n',
          properties: {},
          tags: [],
        },
        blocks: [],
        tasks: [],
        outgoing_links: [],
        backlinks: [],
        graph: null,
      },
    }
    render(<KnowledgeExplorer />)
    fireEvent.change(screen.getByLabelText('knowledge.mounts'), {
      target: { value: 'overlay:overlay_space:default' },
    })
    fireEvent.click(await screen.findByRole('button', { name: target.title }))
    fireEvent.click(screen.getByRole('button', { name: source.title }))

    vaultQueries.page.mockClear()
    vaultQueries.backlinks.mockClear()
    vaultQueries.outgoing.mockClear()
    const pane = screen.getByRole('region', {
      name: 'knowledge.knowledgePane modes pane-1',
    })
    fireEvent.click(within(pane).getByRole('button', {
      name: 'Navigate target Overlay mention',
    }))

    const workspacePane = useKnowledgeWorkspaceStore.getState().panes['pane-1']
    expect(workspacePane.tabs).toHaveLength(2)
    expect(workspacePane.tabs.find((tab) => tab.id === workspacePane.activeTabId))
      .toMatchObject({
        noteId: target.id,
        sourceAuthority: 'overlay',
      })
    expect(vaultQueries.page.mock.calls.every(
      ([vaultId, noteId]) => vaultId === undefined && noteId === undefined,
    )).toBe(true)
    expect(vaultQueries.backlinks.mock.calls.every(
      ([vaultId, noteId]) => vaultId === undefined && noteId === undefined,
    )).toBe(true)
    expect(vaultQueries.outgoing.mock.calls.every(
      ([vaultId, noteId]) => vaultId === undefined && noteId === undefined,
    )).toBe(true)
  })

  it('opens and reuses an unseen incoming overlay graph note by canonical source path', async () => {
    const center = {
      id: 'overlay_note:center',
      source_authority: 'overlay' as const,
      space_id: 'overlay_space:default',
      projected_note_id: 'note:center',
      stable_id: 'stable-overlay-center',
      kind: 'unique' as const,
      date_key: null,
      relative_path: 'Notes/20260729-1600 Center.md',
      title: 'Center',
      content_hash: 'c'.repeat(64),
      revision: 1,
      projection_state: 'current' as const,
      encoding: 'utf-8' as const,
      newline: 'lf' as const,
      created_at: '2026-07-30T00:00:00.000Z',
      updated_at: '2026-07-30T00:00:00.000Z',
    }
    const incoming = {
      ...center,
      id: 'overlay_note:incoming',
      projected_note_id: 'note:incoming',
      stable_id: 'stable-overlay-incoming',
      relative_path: 'Notes/20260729-1601 Incoming.md',
      title: 'Incoming',
      content_hash: 'd'.repeat(64),
    }
    const backlink = {
      ...resolvedLink,
      id: 'note_link:incoming',
      source_note_id: incoming.projected_note_id,
      source_overlay_note_id: incoming.id,
      source_relative_path: incoming.relative_path,
      source_note_title: incoming.title,
      target_note_id: center.projected_note_id,
      target_overlay_note_id: center.id,
      target_note_title: center.title,
      target_relative_path: center.relative_path,
      target_text: center.title,
    }
    overlayQueries.notes = [center, incoming]
    overlayQueries.pages = {
      [center.id]: {
        overlay: center,
        editable_markdown: '# Center\n',
        note: {
          id: center.projected_note_id,
          title: center.title,
          markdown: '# Center\n',
          properties: {},
          tags: [],
        },
        blocks: [],
        tasks: [],
        outgoing_links: [],
        backlinks: [backlink],
        graph: {
          nodes: [
            { id: center.projected_note_id, title: center.title },
            { id: incoming.projected_note_id, title: incoming.title },
          ],
          edges: [{
            id: backlink.id,
            source: incoming.projected_note_id,
            target: center.projected_note_id,
            kind: 'wikilink',
            resolved: true,
          }],
        },
      },
      [incoming.id]: {
        overlay: incoming,
        editable_markdown: '# Incoming\n',
        note: {
          id: incoming.projected_note_id,
          title: incoming.title,
          markdown: '# Incoming\n',
          properties: {},
          tags: [],
        },
        blocks: [],
        tasks: [],
        outgoing_links: [],
        backlinks: [],
        graph: {
          nodes: [{ id: incoming.projected_note_id, title: incoming.title }],
          edges: [],
        },
      },
    }
    render(<KnowledgeExplorer />)
    fireEvent.change(screen.getByLabelText('knowledge.mounts'), {
      target: { value: 'overlay:overlay_space:default' },
    })
    fireEvent.click(await screen.findByRole('button', { name: center.title }))
    fireEvent.click(screen.getByRole('button', { name: 'knowledge.localGraph' }))

    vaultQueries.page.mockClear()
    vaultQueries.backlinks.mockClear()
    vaultQueries.outgoing.mockClear()
    const graphNodeName = `Navigate graph node ${incoming.projected_note_id}`
    fireEvent.click(screen.getByRole('button', { name: graphNodeName }))

    let workspacePane = useKnowledgeWorkspaceStore.getState().panes['pane-1']
    expect(workspacePane.tabs).toHaveLength(2)
    const incomingTab = workspacePane.tabs.find(
      (tab) => tab.noteId === incoming.id,
    )
    expect(incomingTab).toMatchObject({
      noteId: incoming.id,
      relativePath: incoming.relative_path,
      sourceAuthority: 'overlay',
    })
    expect(workspacePane.activeTabId).toBe(incomingTab?.id)

    fireEvent.click(screen.getByRole('tab', { name: `Graph: ${center.title}` }))
    fireEvent.click(screen.getByRole('button', { name: graphNodeName }))

    workspacePane = useKnowledgeWorkspaceStore.getState().panes['pane-1']
    expect(workspacePane.tabs).toHaveLength(2)
    expect(workspacePane.activeTabId).toBe(incomingTab?.id)
    expect(vaultQueries.page.mock.calls.every(
      ([vaultId, noteId]) => vaultId === undefined && noteId === undefined,
    )).toBe(true)
    expect(vaultQueries.backlinks.mock.calls.every(
      ([vaultId, noteId]) => vaultId === undefined && noteId === undefined,
    )).toBe(true)
    expect(vaultQueries.outgoing.mock.calls.every(
      ([vaultId, noteId]) => vaultId === undefined && noteId === undefined,
    )).toBe(true)
  })
})

describe('KnowledgeExplorer utility rail', () => {
  beforeEach(() => {
    states.hydration = { isLoading: false, isError: false }
    states.persistence = { isPending: false, isError: false, error: null }
    pageIdentity.value = null
    navigationQueries.create.mockReset()
    navigationQueries.random.mockReset()
    navigationQueries.restoreWorkspace.mockReset()
    navigationQueries.createWorkspace.mockReset()
    navigationQueries.updateWorkspace.mockReset()
    navigationQueries.duplicateWorkspace.mockReset()
    navigationQueries.deleteWorkspace.mockReset()
    navigationQueries.random.mockResolvedValue({ state: 'empty', document: null })
    navigationQueries.workspaces = { items: [] }
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
  })

  it('switches to bookmarks without replacing the active document', async () => {
    await renderExplorer()
    await selectFile('notes/one.md')
    const activeBefore = useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId

    fireEvent.click(screen.getByRole('button', { name: 'Bookmarks' }))

    expect(screen.getByRole('navigation', { name: 'Bookmarks' })).toBeVisible()
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId).toBe(activeBefore)
  })

  it('does not apply a stale named workspace before confirmation', async () => {
    navigationQueries.workspaces = { items: [{
      id: 'named_knowledge_workspace:research', name: 'Research desk', revision: 4,
      updatedAt: '2026-07-31T00:00:00.000Z',
    }] }
    navigationQueries.restoreWorkspace.mockResolvedValue({
      workspaceId: 'named_knowledge_workspace:research', revision: 4,
      activePaneId: 'pane-1', nextId: 3,
      panes: { 'pane-1': { id: 'pane-1', activeTabId: 'tab-1', tabs: [{
        id: 'tab-1', displayLabel: 'Research note', viewMode: 'reading',
        target: { kind: 'document', documentId: 'knowledge_engine_document:research' },
        targetState: 'stale', targetDocument: null,
      }] } },
      layout: { type: 'pane', paneId: 'pane-1' },
      navigation: useKnowledgeWorkspaceStore.getState().navigation,
      summary: { available: 0, stale: 1, unavailable: 0, missing: 0 },
    })
    await renderExplorer()

    fireEvent.click(screen.getByRole('button', { name: 'Workspaces' }))
    const before = serializeKnowledgeWorkspace(useKnowledgeWorkspaceStore.getState())
    const applyNamedWorkspace = vi.spyOn(useKnowledgeWorkspaceStore.getState(), 'applyNamedWorkspace')
    fireEvent.click(screen.getByRole('button', { name: 'Open Research desk' }))

    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Open workspace with unavailable targets' })).toBeVisible())
    expect(serializeKnowledgeWorkspace(useKnowledgeWorkspaceStore.getState())).toEqual(before)
    expect(applyNamedWorkspace).not.toHaveBeenCalled()
    const revisionBeforeCancel = useKnowledgeWorkspaceStore.getState().revision
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(serializeKnowledgeWorkspace(useKnowledgeWorkspaceStore.getState())).toEqual(before)
    expect(useKnowledgeWorkspaceStore.getState().revision).toBe(revisionBeforeCancel)
  })

  it('applies available targets once and retains empty panes when stale targets are omitted', async () => {
    pageIdentity.value = 'knowledge_engine_document:research'
    navigationQueries.workspaces = { items: [{
      id: 'named_knowledge_workspace:research', name: 'Research desk', revision: 4,
      updatedAt: '2026-07-31T00:00:00.000Z',
    }] }
    navigationQueries.restoreWorkspace.mockResolvedValue({
      workspaceId: 'named_knowledge_workspace:research', revision: 4,
      activePaneId: 'pane-1', nextId: 4,
      panes: {
        'pane-1': { id: 'pane-1', activeTabId: 'tab-1', tabs: [{
          id: 'tab-1', displayLabel: 'Research note', viewMode: 'reading',
          target: { kind: 'document', documentId: 'knowledge_engine_document:research' },
          targetState: 'available', targetDocument: {
            documentId: 'knowledge_engine_document:research', spaceId: 'knowledge_engine_space:research',
            authorityKind: 'external_read_only', sourceKind: 'markdown', title: 'Research note',
            relativeLocator: 'research.md', legacyNoteId: 'note:research', legacyContainerId: 'vault:one',
          },
        }] },
        'pane-2': { id: 'pane-2', activeTabId: 'tab-2', tabs: [{
          id: 'tab-2', displayLabel: 'Gone note', viewMode: 'reading',
          target: { kind: 'document', documentId: 'knowledge_engine_document:gone' },
          targetState: 'missing', targetDocument: null,
        }] },
      },
      layout: { type: 'split', id: 'split-3', direction: 'horizontal', firstSize: 50,
        first: { type: 'pane', paneId: 'pane-1' }, second: { type: 'pane', paneId: 'pane-2' } },
      navigation: useKnowledgeWorkspaceStore.getState().navigation,
      summary: { available: 1, stale: 0, unavailable: 0, missing: 1 },
    })
    await renderExplorer()
    fireEvent.click(screen.getByRole('button', { name: 'Workspaces' }))
    const applyNamedWorkspace = vi.spyOn(useKnowledgeWorkspaceStore.getState(), 'applyNamedWorkspace')
    fireEvent.click(screen.getByRole('button', { name: 'Open Research desk' }))
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Open workspace with unavailable targets' })).toBeVisible())

    fireEvent.click(screen.getByRole('button', { name: 'Open available' }))

    await waitFor(() => expect(applyNamedWorkspace).toHaveBeenCalledOnce())
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs).toHaveLength(1)
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-2']).toMatchObject({ activeTabId: null, tabs: [] })
  })

  it('restores stable block focus and active graph context only for available tab IDs', async () => {
    pageIdentity.value = 'knowledge_engine_document:research'
    navigationQueries.workspaces = { items: [{
      id: 'named_knowledge_workspace:research', name: 'Research desk', revision: 5,
      updatedAt: '2026-07-31T00:00:00.000Z',
    }] }
    const descriptor = {
      documentId: 'knowledge_engine_document:research', spaceId: 'knowledge_engine_space:research',
      authorityKind: 'external_read_only', sourceKind: 'markdown', title: 'Research note',
      relativeLocator: 'research.md', legacyNoteId: 'note:research', legacyContainerId: 'vault:one',
    }
    navigationQueries.restoreWorkspace.mockResolvedValue({
      workspaceId: 'named_knowledge_workspace:research', revision: 5,
      activePaneId: 'pane-2', nextId: 5,
      panes: {
        'pane-1': { id: 'pane-1', activeTabId: 'tab-block', tabs: [
          { id: 'tab-block', displayLabel: 'Focused block', viewMode: 'reading', target: {
            kind: 'block', documentId: descriptor.documentId, blockId: 'knowledge_engine_block:one',
            sourceRevisionId: 'knowledge_engine_revision:one',
          }, targetState: 'available', targetDocument: descriptor },
          { id: 'tab-stale-duplicate', displayLabel: 'Stale duplicate', viewMode: 'reading', target: {
            kind: 'block', documentId: descriptor.documentId, blockId: 'knowledge_engine_block:two',
            sourceRevisionId: 'knowledge_engine_revision:two',
          }, targetState: 'missing', targetDocument: null },
        ] },
        'pane-2': { id: 'pane-2', activeTabId: 'tab-graph', tabs: [{
          id: 'tab-graph', displayLabel: 'Research graph', viewMode: 'graph', target: {
            kind: 'graph', rootDocumentId: descriptor.documentId,
            spaceIds: ['knowledge_engine_space:research'], relationKinds: ['wikilink'],
            viewport: { x: 4, y: 5, zoom: 2 },
          }, targetState: 'available', targetDocument: descriptor,
        }] },
      },
      layout: { type: 'split', id: 'split-4', direction: 'horizontal', firstSize: 50,
        first: { type: 'pane', paneId: 'pane-1' }, second: { type: 'pane', paneId: 'pane-2' } },
      navigation: useKnowledgeWorkspaceStore.getState().navigation,
      summary: { available: 2, stale: 0, unavailable: 0, missing: 1 },
    })
    await renderExplorer()
    fireEvent.click(screen.getByRole('button', { name: 'Workspaces' }))
    states.persistenceWrites.mockClear()
    const setFocusedBlock = vi.spyOn(useKnowledgeWorkspaceStore.getState(), 'setFocusedBlock')
    fireEvent.click(screen.getByRole('button', { name: 'Open Research desk' }))
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Open workspace with unavailable targets' })).toBeVisible())
    fireEvent.click(screen.getByRole('button', { name: 'Open available' }))

    await waitFor(() => expect(setFocusedBlock).toHaveBeenCalledWith('pane-1', 'tab-block', {
      blockId: 'knowledge_engine_block:one', sourceRevisionId: 'knowledge_engine_revision:one',
    }))
    await waitFor(() => expect(useKnowledgeWorkspaceStore.getState().focusedBlocksByTab).toEqual({
      'tab-block': { blockId: 'knowledge_engine_block:one', sourceRevisionId: 'knowledge_engine_revision:one' },
    }))
    expect(useKnowledgeWorkspaceStore.getState().graphBookmarkContext).toEqual({
      rootDocumentId: descriptor.documentId, spaceIds: ['knowledge_engine_space:research'],
      relationKinds: ['wikilink'], viewport: { x: 4, y: 5, zoom: 2 },
    })
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-2'].tabs[0].graphBookmarkContext).toEqual({
      rootDocumentId: descriptor.documentId, spaceIds: ['knowledge_engine_space:research'],
      relationKinds: ['wikilink'], viewport: { x: 4, y: 5, zoom: 2 },
    })
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs.map((tab) => tab.id)).toEqual(['tab-block'])
    expect(states.persistenceWrites).toHaveBeenCalled()
  })

  it('saves only stable target IDs and blocks the save when identity resolution fails', async () => {
    pageIdentity.value = 'knowledge_engine_document:research'
    const { unmount } = await renderExplorer()
    await selectFile('notes/one.md')
    fireEvent.click(screen.getByRole('button', { name: 'Workspaces' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save Current As' }))
    fireEvent.change(screen.getByLabelText('Workspace name'), { target: { value: 'Stable desk' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save workspace' }))
    await waitFor(() => expect(navigationQueries.createWorkspace).toHaveBeenCalledOnce())
    const savedWorkspace = navigationQueries.createWorkspace.mock.calls.at(0) as unknown as [{ snapshot: unknown }]
    const serialized = JSON.stringify(savedWorkspace[0].snapshot)
    expect(serialized).toContain('knowledge_engine_document:research')
    expect(serialized).not.toContain('note:one')
    expect(serialized).not.toContain('notes/one.md')

    unmount()
    navigationQueries.createWorkspace.mockClear()
    pageIdentity.value = null
    act(() => useKnowledgeWorkspaceStore.getState().resetWorkspace())
    await renderExplorer()
    await selectFile('notes/one.md')
    fireEvent.click(screen.getByRole('button', { name: 'Workspaces' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save Current As' }))
    fireEvent.change(screen.getByLabelText('Workspace name'), { target: { value: 'Unavailable desk' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save workspace' }))
    await waitFor(() => expect(screen.getByText('Workspace could not be saved. Check the knowledge engine and try again.')).toBeVisible())
    expect(navigationQueries.createWorkspace).not.toHaveBeenCalled()
  })

  it('persists a keyboard-resized utility sidebar within its safe bounds', async () => {
    await renderExplorer()
    const width = useKnowledgeWorkspaceStore.getState().navigation.sidebarWidth

    fireEvent.keyDown(screen.getByRole('separator', { name: 'Resize utility sidebar' }), { key: 'ArrowRight' })

    expect(useKnowledgeWorkspaceStore.getState().navigation.sidebarWidth).toBe(Math.min(640, width + 16))
  })

  it('clamps pointer sidebar resizing and exposes its accessible value', async () => {
    await renderExplorer()
    const handle = screen.getByRole('separator', { name: 'Resize utility sidebar' })

    fireEvent.mouseDown(handle, { clientX: 100 })
    fireEvent.mouseMove(handle, { clientX: 9_000 })
    fireEvent.mouseUp(handle)

    expect(useKnowledgeWorkspaceStore.getState().navigation.sidebarWidth).toBe(640)
    expect(handle).toHaveAttribute('aria-valuenow', '640')
  })

  it('hydrates a valid page unified ID without replacing the active tab or focus', async () => {
    pageIdentity.value = 'knowledge_engine_document:research'
    await renderExplorer()
    await selectFile('notes/one.md')
    const pane = screen.getByRole('region', { name: 'knowledge.knowledgePane modes pane-1' })
    pane.focus()
    const activeBefore = useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId

    await waitFor(() => expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0])
      .toMatchObject({ knowledgeDocumentId: 'knowledge_engine_document:research' }))
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId).toBe(activeBefore)
    expect(document.activeElement).toBe(pane)
    expect(screen.getByRole('button', { name: 'Bookmark Current Target' })).toBeEnabled()
  })

  it('keeps Bookmark Current Target disabled for an absent or malformed page ID', async () => {
    pageIdentity.value = 'not-a-unified-id'
    await renderExplorer()
    await selectFile('notes/one.md')

    await waitFor(() => expect(screen.getByRole('button', { name: 'Bookmark Current Target' })).toBeDisabled())
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0].knowledgeDocumentId).toBeNull()
  })

  it('sends persisted filters to Random Note and leaves the active tab unchanged for an empty result', async () => {
    navigationQueries.random.mockResolvedValueOnce({ state: 'empty', document: null })
    useKnowledgeWorkspaceStore.getState().setNavigation({
      selectedSpaceIds: ['knowledge_engine_space:research'],
      authorityFilters: ['external_read_only'],
      bookmarkTags: ['plans'],
    })
    await renderExplorer()
    await selectFile('notes/one.md')
    const activeBefore = useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId

    fireEvent.click(screen.getByRole('button', { name: 'Random Note' }))

    await waitFor(() => expect(navigationQueries.random).toHaveBeenCalledWith({
      spaceIds: ['knowledge_engine_space:research'], authorityKinds: ['external_read_only'], tags: ['plans'],
    }))
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId).toBe(activeBefore)
  })

  it('creates a stable block target for the focused unified block rather than a path target', async () => {
    pageIdentity.value = 'knowledge_engine_document:research'
    await renderExplorer()
    await selectFile('notes/one.md')
    await waitFor(() => expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0].knowledgeDocumentId)
      .toBe('knowledge_engine_document:research'))
    const activeTabId = useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId!
    act(() => useKnowledgeWorkspaceStore.getState().setFocusedBlock('pane-1', activeTabId, {
      blockId: 'knowledge_engine_block:heading', sourceRevisionId: null,
    }))

    fireEvent.click(screen.getByRole('button', { name: 'Bookmark Current Target' }))

    await waitFor(() => expect(navigationQueries.create).toHaveBeenCalledWith(expect.objectContaining({
      target: {
        kind: 'block', documentId: 'knowledge_engine_document:research',
        blockId: 'knowledge_engine_block:heading', sourceRevisionId: null,
      },
    })))
    expect(JSON.stringify(navigationQueries.create.mock.calls.at(-1))).not.toContain('/Users/')
  })

  it('uses live graph root, filters, and controlled viewport for a graph bookmark', async () => {
    pageIdentity.value = 'knowledge_engine_document:graph-root'
    useKnowledgeWorkspaceStore.getState().openTab({
      vaultId: 'vault:one', noteId: 'note:one', title: 'One', relativePath: 'notes/one.md',
      knowledgeDocumentId: 'knowledge_engine_document:graph-root', viewMode: 'graph',
      graphViewport: { x: 1, y: 2, zoom: 1.5 },
    })
    useKnowledgeWorkspaceStore.getState().setGraphBookmarkContext({
      rootDocumentId: 'knowledge_engine_document:graph-root',
      spaceIds: ['knowledge_engine_space:research'], relationKinds: ['wikilink'],
      viewport: { x: 4, y: 5, zoom: 2 },
    })
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0]).toMatchObject({
      viewMode: 'graph', knowledgeDocumentId: 'knowledge_engine_document:graph-root',
    })
    await renderExplorer()
    await act(async () => undefined)

    fireEvent.click(screen.getByRole('button', { name: 'Bookmark Current Target' }))

    await waitFor(() => expect(navigationQueries.create).toHaveBeenCalledWith(expect.objectContaining({
      target: {
        kind: 'graph', rootDocumentId: 'knowledge_engine_document:graph-root',
        spaceIds: ['knowledge_engine_space:research'], relationKinds: ['wikilink'],
        viewport: { x: 4, y: 5, zoom: 2 },
      },
    })))
  })

  it('hydrates a safe Overlay page unified ID without replacing the active tab', async () => {
    const overlayId = 'overlay_note:unique'
    overlayQueries.pages = {
      [overlayId]: {
        knowledge_document_id: 'knowledge_engine_document:overlay',
        overlay: {
          id: overlayId, source_authority: 'overlay', space_id: 'overlay_space:default',
          projected_note_id: 'projected:unique', stable_id: 'a'.repeat(20), kind: 'unique', date_key: null,
          relative_path: 'Notes/Overlay.md', title: 'Overlay', content_hash: 'a'.repeat(64), revision: 1,
          projection_state: 'current', encoding: 'utf-8', newline: 'lf',
          created_at: '2026-07-31T00:00:00.000Z', updated_at: '2026-07-31T00:00:00.000Z',
        },
        editable_markdown: '# Overlay', note: { id: 'projected:unique', title: 'Overlay', content: '# Overlay', properties: {}, tags: [] },
        blocks: [], tasks: [], outgoing_links: [], backlinks: [], graph: null,
      },
    }
    useKnowledgeWorkspaceStore.getState().openTab({
      vaultId: 'overlay_space:default', noteId: overlayId, title: 'Overlay', relativePath: 'Notes/Overlay.md', sourceAuthority: 'overlay',
    })
    const tabId = useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId
    await renderExplorer()

    await waitFor(() => expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0]).toMatchObject({
      knowledgeDocumentId: 'knowledge_engine_document:overlay',
    }))
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].activeTabId).toBe(tabId)
    expect(screen.getByRole('button', { name: 'Bookmark Current Target' })).toBeEnabled()
  })
})

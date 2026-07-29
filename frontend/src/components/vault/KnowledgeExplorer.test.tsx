import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import {
  resetKnowledgeCommandContextStore,
  useKnowledgeCommandContextStore,
} from '@/lib/commands/knowledge-command-context-store'

const states = vi.hoisted(() => ({
  page: { isLoading: false, isError: false },
  graph: { isLoading: false, isError: false },
  links: { isLoading: false, isError: false },
  hydration: { isLoading: false, isError: false },
  persistence: { isPending: false, isError: false, error: null as Error | null },
}))
const vaultQueries = vi.hoisted(() => ({
  page: vi.fn(),
  backlinks: vi.fn(),
  outgoing: vi.fn(),
  scan: vi.fn(async () => undefined),
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
    data: [{
      id: 'vault:one',
      name: 'Fixture',
      format_mode: 'markdown',
      state: 'ready-read-only',
      watch_enabled: true,
    }],
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
  useScanVault: (vaultId: string) => ({
    mutateAsync: () => vaultQueries.scan(vaultId),
    isPending: false,
  }),
}))

vi.mock('@/lib/hooks/use-knowledge-workspace', () => ({
  useHydrateKnowledgeWorkspace: () => states.hydration,
  usePersistKnowledgeWorkspace: () => states.persistence,
}))

vi.mock('@/lib/hooks/use-knowledge-command-data', () => ({
  useKnowledgeCatalog: () => ({
    candidates: [],
    isLoading: false,
    failedVaultCount: 0,
    retryFailedVaults: vi.fn(async () => undefined),
  }),
}))

vi.mock('./VaultGraph', () => ({
  VaultGraph: ({
    onNavigate,
  }: {
    onNavigate: (noteId: string) => void
  }) => (
    <div>
      Local graph content
      <button type="button" onClick={() => onNavigate('note:graph-linked')}>
        Navigate graph node
      </button>
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
    states.page = { isLoading: false, isError: false }
    states.graph = { isLoading: false, isError: false }
    states.links = { isLoading: false, isError: false }
    states.hydration = { isLoading: false, isError: false }
    states.persistence = { isPending: false, isError: false, error: null }
    vi.clearAllMocks()
    resetKnowledgeCommandContextStore()
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

  it('clears its command registration on unmount', async () => {
    const { unmount } = await renderExplorer()
    expect(useKnowledgeCommandContextStore.getState().context?.selectedVaultId)
      .toBe('vault:one')
    unmount()
    expect(useKnowledgeCommandContextStore.getState().context).toBeNull()
  })

  it('delegates scan commands only to the selected mount', async () => {
    await renderExplorer()
    await useKnowledgeCommandContextStore.getState().context?.scanSelectedVault?.()
    expect(vaultQueries.scan).toHaveBeenCalledWith('vault:one')
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
    useKnowledgeWorkspaceStore.getState().replaceWorkspace({
      version: 1,
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
          }],
        },
      },
      layout: { type: 'pane', paneId: 'pane-1' },
    })

    await renderExplorer()

    expect(screen.getByRole('tab', { name: 'Persisted one' }))
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

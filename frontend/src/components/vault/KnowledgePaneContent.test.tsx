import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { VaultPage } from '@/lib/api/vault'
import { VaultPageContractError } from '@/lib/api/vault'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'

const editorState = vi.hoisted(() => ({ failLivePreview: false }))
const queries = vi.hoisted(() => ({
  page: {
    data: undefined as VaultPage | undefined,
    isLoading: false,
    isError: false,
    error: null as Error | null,
  },
  graph: vi.fn(),
}))

vi.mock('@/lib/hooks/use-vault', () => ({
  useVaultPage: () => queries.page,
  useVaultOutgoing: () => ({ data: [], isLoading: false, isError: false }),
  useVaultGraph: (vaultId?: string, noteId?: string, enabled?: boolean) => {
    queries.graph(vaultId, noteId, enabled)
    return {
      data: { nodes: [], edges: [] },
      isLoading: false,
      isError: false,
    }
  },
}))

vi.mock('./VaultLivePreview', () => ({
  VaultLivePreview: ({ title }: { title: string }) => {
    if (editorState.failLivePreview) throw new Error('live preview failed')
    return <section aria-label={`${title} live preview`} />
  },
}))

vi.mock('./VaultSourceView', () => ({
  VaultSourceView: ({ title }: { title: string }) => (
    <section aria-label={`${title} source`}>
      <input aria-label={`${title} source input`} />
      <textarea aria-label={`${title} source textarea`} />
      <select aria-label={`${title} source select`}>
        <option>Fixture</option>
      </select>
      <div aria-label={`${title} source editable`} contentEditable />
    </section>
  ),
}))

vi.mock('./VaultMarkdown', () => ({
  VaultMarkdown: ({ markdown }: { markdown: string }) => <div>{markdown}</div>,
}))

vi.mock('./VaultGraph', () => ({
  VaultGraph: () => <div>Local graph content</div>,
}))

import { KnowledgePaneContent } from './KnowledgePaneContent'

const pageFixture = {
  file: {
    id: 'file:plan',
    note_id: 'note:plan',
    vault_id: 'vault:one',
    relative_path: 'pages/plan.md',
    file_kind: 'note',
    format: 'markdown',
    content_hash: 'a'.repeat(64),
    parse_status: 'parsed',
    size_bytes: 6,
    modified_ns: 1,
    encoding: 'utf-8',
    newline: 'lf',
    deleted_state: 'present',
  },
  note: {
    id: 'note:plan',
    title: 'Canonical Plan',
    content: '# Plan',
    properties: {},
    tags: [],
  },
  blocks: [],
  tasks: [],
  outgoing_links: [],
  backlinks: [],
} satisfies VaultPage

function replaceWorkspace(viewMode: 'reading' | 'source' | 'live-preview' | 'graph' = 'reading') {
  useKnowledgeWorkspaceStore.getState().replaceWorkspace({
    version: 1,
    activePaneId: 'pane-1',
    nextId: 2,
    panes: {
      'pane-1': {
        id: 'pane-1',
        activeTabId: 'tab-1',
        tabs: [{
          id: 'tab-1',
          vaultId: 'vault:one',
          noteId: 'note:plan',
          title: 'Stale Plan',
          relativePath: 'synthetic/stale.md',
          viewMode,
          sourceAuthority: 'external-vault',
        }],
      },
    },
    layout: { type: 'pane', paneId: 'pane-1' },
  })
}

function PaneHarness() {
  const pane = useKnowledgeWorkspaceStore((state) => state.panes['pane-1'])
  return (
    <KnowledgePaneContent
      pane={pane}
      mounts={[{
        id: 'vault:one',
        name: 'Research',
        format_mode: 'markdown',
        state: 'ready-read-only',
        watch_enabled: true,
      }]}
      onNavigate={vi.fn()}
    />
  )
}

function renderPane() {
  return render(<PaneHarness />)
}

function replaceTwoPaneWorkspace() {
  useKnowledgeWorkspaceStore.getState().replaceWorkspace({
    version: 1,
    activePaneId: 'pane-1',
    nextId: 3,
    panes: {
      'pane-1': {
        id: 'pane-1',
        activeTabId: 'tab-1',
        tabs: [{
          id: 'tab-1',
          vaultId: 'vault:one',
          noteId: 'note:plan',
          title: 'Pane One',
          relativePath: 'pages/one.md',
          viewMode: 'source',
          sourceAuthority: 'external-vault',
        }],
      },
      'pane-2': {
        id: 'pane-2',
        activeTabId: 'tab-2',
        tabs: [{
          id: 'tab-2',
          vaultId: 'vault:one',
          noteId: 'note:plan',
          title: 'Pane Two',
          relativePath: 'pages/two.md',
          viewMode: 'reading',
          sourceAuthority: 'external-vault',
        }],
      },
    },
    layout: {
      type: 'split',
      id: 'split-1',
      direction: 'horizontal',
      first: { type: 'pane', paneId: 'pane-1' },
      second: { type: 'pane', paneId: 'pane-2' },
    },
  })
}

function TwoPaneHarness() {
  const panes = useKnowledgeWorkspaceStore((state) => state.panes)
  return (
    <>
      <KnowledgePaneContent pane={panes['pane-1']} mounts={[]} onNavigate={vi.fn()} />
      <KnowledgePaneContent pane={panes['pane-2']} mounts={[]} onNavigate={vi.fn()} />
    </>
  )
}

describe('KnowledgePaneContent', () => {
  beforeEach(() => {
    editorState.failLivePreview = false
    queries.page = {
      data: pageFixture,
      isLoading: false,
      isError: false,
      error: null,
    }
    queries.graph.mockClear()
    replaceWorkspace()
  })

  it('reconciles canonical tab identity and persists all four modes', async () => {
    renderPane()
    await waitFor(() => {
      expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0])
        .toMatchObject({
          title: 'Canonical Plan',
          relativePath: 'pages/plan.md',
        })
    })

    for (const [label, mode] of [
      ['knowledge.reader', 'reading'],
      ['knowledge.source', 'source'],
      ['knowledge.livePreview', 'live-preview'],
      ['knowledge.localGraph', 'graph'],
    ] as const) {
      fireEvent.click(screen.getByRole('button', { name: label }))
      expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0].viewMode)
        .toBe(mode)
    }
  })

  it('switches modes with region-scoped Control number shortcuts only', () => {
    renderPane()
    const region = screen.getByRole('region', {
      name: 'knowledge.knowledgePane modes pane-1',
    })

    fireEvent.keyDown(region, { key: '3', ctrlKey: true })
    expect(screen.getByLabelText('Canonical Plan live preview'))
      .toBeInTheDocument()

    fireEvent.keyDown(window, { key: '2', ctrlKey: true })
    expect(screen.queryByLabelText('Canonical Plan source'))
      .not.toBeInTheDocument()

    fireEvent.keyDown(region, { key: '2', ctrlKey: true, metaKey: true })
    expect(screen.queryByLabelText('Canonical Plan source'))
      .not.toBeInTheDocument()
  })

  it.each([
    ['without Control', {}],
    ['with Shift', { ctrlKey: true, shiftKey: true }],
    ['with Meta', { ctrlKey: true, metaKey: true }],
    ['with Alt', { ctrlKey: true, altKey: true }],
    ['when repeated', { ctrlKey: true, repeat: true }],
  ] as const)('ignores Control-number shortcuts %s', (_label, modifiers) => {
    renderPane()
    const region = screen.getByRole('region', {
      name: 'knowledge.knowledgePane modes pane-1',
    })

    fireEvent.keyDown(region, { key: '3', ...modifiers })

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0].viewMode)
      .toBe('reading')
  })

  it.each(['input', 'textarea', 'select', 'editable'] as const)(
    'ignores Control-number shortcuts from a descendant %s',
    (descendant) => {
      replaceWorkspace('source')
      renderPane()
      const target = screen.getByLabelText(`Canonical Plan source ${descendant}`)

      fireEvent.keyDown(target, { key: '3', ctrlKey: true })

      expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0].viewMode)
        .toBe('source')
    },
  )

  it.each([
    ['1', 'reading'],
    ['2', 'source'],
    ['3', 'live-preview'],
    ['4', 'graph'],
  ] as const)(
    'keeps Control+%s scoped to the focused pane',
    (key, expectedMode) => {
      replaceTwoPaneWorkspace()
      render(<TwoPaneHarness />)
      const paneTwoRegion = screen.getByRole('region', {
        name: 'knowledge.knowledgePane modes pane-2',
      })

      fireEvent.keyDown(paneTwoRegion, { key, ctrlKey: true })

      const workspace = useKnowledgeWorkspaceStore.getState()
      expect(workspace.panes['pane-1'].tabs[0].viewMode).toBe('source')
      expect(workspace.panes['pane-2'].tabs[0].viewMode).toBe(expectedMode)
      expect(within(paneTwoRegion).getByRole('button', {
        name: expectedMode === 'reading'
          ? 'knowledge.reader'
          : expectedMode === 'source'
            ? 'knowledge.source'
            : expectedMode === 'live-preview'
              ? 'knowledge.livePreview'
              : 'knowledge.localGraph',
      })).toHaveAttribute('aria-pressed', 'true')
    },
  )

  it('does not reconcile or display stale page data during a refetch error', () => {
    queries.page = {
      data: pageFixture,
      isLoading: false,
      isError: true,
      error: new Error('refetch failed'),
    }

    renderPane()

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0])
      .toMatchObject({
        title: 'Stale Plan',
        relativePath: 'synthetic/stale.md',
      })
    expect(screen.getByText('knowledge.loadError')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Canonical Plan' }))
      .not.toBeInTheDocument()
  })

  it('enables the graph query only for the persisted Graph mode', () => {
    const { rerender } = renderPane()
    expect(queries.graph).toHaveBeenLastCalledWith(
      'vault:one',
      'note:plan',
      false,
    )

    replaceWorkspace('graph')
    rerender(<PaneHarness />)
    expect(queries.graph).toHaveBeenLastCalledWith(
      'vault:one',
      'note:plan',
      true,
    )
  })

  it('shows Reading after editor failure without mutating the persisted mode', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    editorState.failLivePreview = true
    replaceWorkspace('live-preview')

    try {
      renderPane()
      expect(screen.getByLabelText('Canonical Plan reading view'))
        .toBeInTheDocument()
      expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0].viewMode)
        .toBe('live-preview')
    } finally {
      consoleError.mockRestore()
    }
  })

  it('resets the display fallback when the canonical content hash changes', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    editorState.failLivePreview = true
    replaceWorkspace('live-preview')

    try {
      const { rerender } = renderPane()
      expect(screen.getByLabelText('Canonical Plan reading view'))
        .toBeInTheDocument()

      editorState.failLivePreview = false
      queries.page = {
        ...queries.page,
        data: {
          ...pageFixture,
          file: { ...pageFixture.file, content_hash: 'b'.repeat(64) },
        },
      }
      rerender(<PaneHarness />)

      expect(screen.getByLabelText('Canonical Plan live preview'))
        .toBeInTheDocument()
    } finally {
      consoleError.mockRestore()
    }
  })

  it.each([
    ['canonical-path-unavailable', 'knowledge.canonicalPathUnavailable'],
    ['page-invalid', 'knowledge.pageInvalid'],
  ] as const)('renders %s without opening a document mode', (code, message) => {
    queries.page = {
      data: undefined,
      isLoading: false,
      isError: true,
      error: new VaultPageContractError(code),
    }

    renderPane()
    expect(screen.getByText(message)).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/reading view|source|live preview/i))
      .not.toBeInTheDocument()
  })

  it('retains a distinct generic page-load error', () => {
    queries.page = {
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('network failed'),
    }

    renderPane()
    expect(screen.getByText('knowledge.loadError')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
})

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { OverlayPage } from '@/lib/api/overlay'
import type { VaultPage } from '@/lib/api/vault'
import { VaultPageContractError } from '@/lib/api/vault'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'

const editorState = vi.hoisted(() => ({ failLivePreview: false }))
const overlayView = vi.hoisted(() => ({
  onReload: undefined as undefined | (() => Promise<unknown>),
  onNavigate: undefined as undefined | ((noteId: string) => void),
}))
const vaultMarkdownView = vi.hoisted(() => ({
  onNavigate: undefined as undefined | ((noteId: string) => void),
}))
const queries = vi.hoisted(() => ({
  page: {
    data: undefined as VaultPage | undefined,
    isLoading: false,
    isError: false,
    error: null as Error | null,
  },
  overlayPage: {
    data: undefined as import('@/lib/api/overlay').OverlayPage | undefined,
    isLoading: false,
    isError: false,
    error: null as Error | null,
    refetch: vi.fn(),
  },
  vaultPageArgs: vi.fn(),
  vaultOutgoingArgs: vi.fn(),
  graph: vi.fn(),
  overlayPageArgs: vi.fn(),
  outgoingLinks: [] as VaultPage['outgoing_links'],
}))

vi.mock('@/lib/hooks/use-vault', () => ({
  useVaultPage: (vaultId?: string, noteId?: string) => {
    queries.vaultPageArgs(vaultId, noteId)
    return queries.page
  },
  useVaultOutgoing: (vaultId?: string, noteId?: string) => {
    queries.vaultOutgoingArgs(vaultId, noteId)
    return { data: queries.outgoingLinks, isLoading: false, isError: false }
  },
  useVaultGraph: (vaultId?: string, noteId?: string, enabled?: boolean) => {
    queries.graph(vaultId, noteId, enabled)
    return {
      data: { nodes: [], edges: [] },
      isLoading: false,
      isError: false,
    }
  },
}))

vi.mock('@/lib/hooks/use-overlay', () => ({
  useOverlayPage: (noteId?: string) => {
    queries.overlayPageArgs(noteId)
    return queries.overlayPage
  },
}))

vi.mock('@/components/overlay/OverlayDocumentView', () => ({
  OverlayDocumentView: ({
    mode,
    onReload,
    onNavigate,
  }: {
    mode: string
    onReload: () => Promise<unknown>
    onNavigate: (noteId: string) => void
  }) => {
    overlayView.onReload = onReload
    overlayView.onNavigate = onNavigate
    return <section aria-label={`Overlay document ${mode}`} />
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
  VaultMarkdown: ({
    markdown,
    onNavigate,
  }: {
    markdown: string
    onNavigate: (noteId: string) => void
  }) => {
    vaultMarkdownView.onNavigate = onNavigate
    return <div>{markdown}</div>
  },
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

function overlayPageWithTarget(
  targetOverlayNoteId: string | null,
): OverlayPage {
  return {
    overlay: {
      id: 'overlay_note:research',
      source_authority: 'overlay',
      space_id: 'overlay_space:default',
      projected_note_id: 'note:research',
      stable_id: 'stable-overlay-research',
      kind: 'unique',
      date_key: null,
      relative_path: 'Notes/20260729-1542 Research.md',
      title: 'Research',
      content_hash: 'b'.repeat(64),
      revision: 2,
      projection_state: 'current',
      encoding: 'utf-8',
      newline: 'lf',
      created_at: '2026-07-29T12:00:00+00:00',
      updated_at: '2026-07-29T12:00:00+00:00',
    },
    editable_markdown: '# Research\n',
    note: {
      id: 'note:research',
      title: 'Research',
      markdown: '# Research\n',
    },
    blocks: [],
    tasks: [],
    outgoing_links: [{
      id: 'note_link:target',
      source_note_id: 'note:research',
      source_overlay_note_id: 'overlay_note:research',
      source_relative_path: 'Notes/20260729-1542 Research.md',
      target_note_id: 'note:target',
      target_overlay_note_id: targetOverlayNoteId,
      target_note_title: 'Target',
      target_relative_path: 'Notes/20260729-1543 Target.md',
      target_text: 'Target',
      link_kind: 'wikilink',
      resolved: true,
      source_start: 0,
      source_end: 10,
    }],
    backlinks: [],
    graph: null,
  }
}

function overlayGraphPage(): OverlayPage {
  const page = overlayPageWithTarget('overlay_note:target')
  return {
    ...page,
    backlinks: [{
      id: 'note_link:source',
      source_note_id: 'note:source',
      source_overlay_note_id: 'overlay_note:source',
      source_relative_path: 'Notes/20260729-1541 Source.md',
      source_note_title: 'Source',
      target_note_id: 'note:research',
      target_overlay_note_id: 'overlay_note:research',
      target_note_title: 'Research',
      target_relative_path: 'Notes/20260729-1542 Research.md',
      target_text: 'Research',
      link_kind: 'wikilink',
      resolved: true,
      source_start: 0,
      source_end: 10,
    }],
    graph: {
      nodes: [
        { id: 'note:research', title: 'Research' },
        { id: 'note:target', title: 'Target' },
        { id: 'note:source', title: 'Source' },
      ],
      edges: [
        {
          id: 'note_link:target',
          source: 'note:research',
          target: 'note:target',
          kind: 'wikilink',
          resolved: true,
        },
        {
          id: 'note_link:source',
          source: 'note:source',
          target: 'note:research',
          kind: 'wikilink',
          resolved: true,
        },
      ],
    },
  }
}

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

function replaceOverlayWorkspace(
  viewMode: 'reading' | 'source' | 'live-preview' | 'graph' = 'source',
) {
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
          vaultId: 'overlay_space:default',
          noteId: 'overlay_note:research',
          title: 'Research',
          relativePath: 'Unique/research.md',
          viewMode,
          sourceAuthority: 'overlay',
        }],
      },
    },
    layout: { type: 'pane', paneId: 'pane-1' },
  })
}

function PaneHarness({
  onNavigate = vi.fn(),
}: {
  onNavigate?: ComponentProps<typeof KnowledgePaneContent>['onNavigate']
}) {
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
      onNavigate={onNavigate}
    />
  )
}

function renderPane(
  onNavigate?: ComponentProps<typeof KnowledgePaneContent>['onNavigate'],
) {
  return render(<PaneHarness onNavigate={onNavigate} />)
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
    queries.vaultPageArgs.mockClear()
    queries.vaultOutgoingArgs.mockClear()
    queries.overlayPageArgs.mockClear()
    queries.outgoingLinks = []
    overlayView.onReload = undefined
    overlayView.onNavigate = undefined
    vaultMarkdownView.onNavigate = undefined
    queries.overlayPage = {
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }
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

  it('routes external authority only to vault data paths', () => {
    replaceWorkspace('source')
    renderPane()

    expect(queries.vaultPageArgs).toHaveBeenLastCalledWith(
      'vault:one',
      'note:plan',
    )
    expect(queries.vaultOutgoingArgs).toHaveBeenLastCalledWith(
      'vault:one',
      'note:plan',
    )
    expect(queries.overlayPageArgs).toHaveBeenLastCalledWith(undefined)
    expect(screen.getByLabelText('Canonical Plan source')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Overlay document/)).not.toBeInTheDocument()
  })

  it('routes overlay authority only to overlay page data, including graph and links', () => {
    replaceOverlayWorkspace('graph')
    queries.overlayPage = {
      data: {
        overlay: {
          id: 'overlay_note:research',
          source_authority: 'overlay',
          space_id: 'overlay_space:default',
          projected_note_id: 'note:research',
          stable_id: 'stable-research-note-1',
          kind: 'unique',
          date_key: null,
          relative_path: 'Unique/research.md',
          title: 'Research',
          content_hash: 'b'.repeat(64),
          revision: 2,
          projection_state: 'current',
          encoding: 'utf-8',
          newline: 'lf',
          created_at: '2026-07-29T12:00:00+00:00',
          updated_at: '2026-07-29T12:00:00+00:00',
        },
        editable_markdown: '# Research\n',
        note: { id: 'note:research', title: 'Research', markdown: '# Research\n' },
        blocks: [],
        tasks: [],
        outgoing_links: [],
        backlinks: [],
        graph: { nodes: [], edges: [] },
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }

    renderPane()

    expect(queries.overlayPageArgs).toHaveBeenLastCalledWith(
      'overlay_note:research',
    )
    expect(queries.vaultPageArgs).toHaveBeenLastCalledWith(undefined, undefined)
    expect(queries.vaultOutgoingArgs).toHaveBeenLastCalledWith(undefined, undefined)
    expect(queries.graph).toHaveBeenLastCalledWith(undefined, undefined, false)
    expect(screen.getByLabelText('Overlay document graph')).toBeInTheDocument()
    expect(screen.queryByLabelText(/source$/)).not.toBeInTheDocument()
  })

  it('rejects a resolved overlay refetch error instead of returning stale data', async () => {
    replaceOverlayWorkspace()
    const stalePage = {
      overlay: {
        id: 'overlay_note:research',
        source_authority: 'overlay' as const,
        space_id: 'overlay_space:default',
        projected_note_id: 'note:research',
        stable_id: 'stable-research-note-1',
        kind: 'unique' as const,
        date_key: null,
        relative_path: 'Unique/research.md',
        title: 'Research',
        content_hash: 'b'.repeat(64),
        revision: 2,
        projection_state: 'current' as const,
        encoding: 'utf-8' as const,
        newline: 'lf' as const,
        created_at: '2026-07-29T12:00:00+00:00',
        updated_at: '2026-07-29T12:00:00+00:00',
      },
      editable_markdown: '# Research\n',
      note: { id: 'note:research', title: 'Research', markdown: '# Research\n' },
      blocks: [],
      tasks: [],
      outgoing_links: [],
      backlinks: [],
      graph: { nodes: [], edges: [] },
    }
    const refetchError = new Error('refresh failed')
    queries.overlayPage = {
      data: stalePage,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn().mockResolvedValue({
        data: stalePage,
        isError: true,
        error: refetchError,
      }),
    }

    renderPane()

    await expect(overlayView.onReload?.()).rejects.toBe(refetchError)
  })

  it('translates a projected overlay link target to its explicit overlay identity', () => {
    replaceOverlayWorkspace()
    queries.overlayPage = {
      data: overlayPageWithTarget('overlay_note:target'),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }
    const onNavigate = vi.fn()

    renderPane(onNavigate)
    overlayView.onNavigate?.('note:target')

    expect(onNavigate).toHaveBeenCalledWith(
      'overlay_space:default',
      'overlay_note:target',
      'Notes/20260729-1543 Target.md',
      'Target',
      'pane-1',
      'Target',
      'overlay',
    )
  })

  it('does not navigate an overlay link without an explicit overlay target', () => {
    replaceOverlayWorkspace()
    queries.overlayPage = {
      data: overlayPageWithTarget(null),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }
    const onNavigate = vi.fn()

    renderPane(onNavigate)
    overlayView.onNavigate?.('note:target')

    expect(onNavigate).not.toHaveBeenCalled()
  })

  it.each([
    {
      direction: 'outgoing',
      projectedId: 'note:target',
      overlayId: 'overlay_note:target',
      relativePath: 'Notes/20260729-1543 Target.md',
      title: 'Target',
      targetText: 'Target',
    },
    {
      direction: 'incoming',
      projectedId: 'note:source',
      overlayId: 'overlay_note:source',
      relativePath: 'Notes/20260729-1541 Source.md',
      title: 'Source',
      targetText: 'Source',
    },
    {
      direction: 'center',
      projectedId: 'note:research',
      overlayId: 'overlay_note:research',
      relativePath: 'Notes/20260729-1542 Research.md',
      title: 'Research',
      targetText: 'Research',
    },
  ])(
    'translates an overlay graph $direction node through explicit identities',
    ({
      projectedId,
      overlayId,
      relativePath,
      title,
      targetText,
    }) => {
      replaceOverlayWorkspace('graph')
      queries.overlayPage = {
        data: overlayGraphPage(),
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      }
      const onNavigate = vi.fn()

      renderPane(onNavigate)
      overlayView.onNavigate?.(projectedId)

      expect(onNavigate).toHaveBeenCalledWith(
        'overlay_space:default',
        overlayId,
        relativePath,
        title,
        'pane-1',
        targetText,
        'overlay',
      )
    },
  )

  it('preserves external link text when navigating a vault note', () => {
    const link: VaultPage['outgoing_links'][number] = {
      id: 'note_link:external-target',
      source_note_id: 'note:plan',
      target_note_id: 'note:target',
      target_note_title: 'Target',
      target_relative_path: 'notes/target.md',
      target_text: 'Human label',
      link_kind: 'wikilink',
      resolved: true,
      source_start: 0,
      source_end: 11,
    }
    queries.page = {
      data: {
        ...pageFixture,
        outgoing_links: [link],
      },
      isLoading: false,
      isError: false,
      error: null,
    }
    queries.outgoingLinks = [link]
    const onNavigate = vi.fn()

    renderPane(onNavigate)
    vaultMarkdownView.onNavigate?.('note:target')

    expect(onNavigate).toHaveBeenCalledWith(
      'vault:one',
      'note:target',
      'notes/target.md',
      'Target',
      'pane-1',
      'Human label',
      'external-vault',
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

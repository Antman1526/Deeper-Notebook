import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useEffect, type ComponentProps } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { OverlayPage } from '@/lib/api/overlay'
import type { VaultCanvasDocument, VaultPage } from '@/lib/api/vault'
import { VaultPageContractError } from '@/lib/api/vault'
import {
  parseKnowledgeWorkspace,
  serializeKnowledgeWorkspace,
  type GraphViewport,
} from '@/lib/api/knowledge-workspace'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'

const editorState = vi.hoisted(() => ({ failLivePreview: false }))
const overlayView = vi.hoisted(() => ({
  onReload: undefined as undefined | (() => Promise<unknown>),
  onNavigate: undefined as undefined | ((noteId: string) => void),
  onMarkdownChange: undefined as undefined | ((markdown: string) => void),
  restoredMarkdown: undefined as string | undefined,
  graphViewport: undefined as GraphViewport | undefined,
  onGraphViewportChange: undefined as undefined | ((viewport: GraphViewport) => void),
}))
const metricFooter = vi.hoisted(() => ({
  props: undefined as undefined | {
    text: string
    selectionText: string
    visible: boolean
    hasDocument: boolean
    emptyLabel: string
  },
}))
const vaultGraphView = vi.hoisted(() => ({
  viewport: undefined as GraphViewport | undefined,
  relationKinds: undefined as string[] | undefined,
  rootDocumentId: undefined as string | null | undefined,
  spaceIds: undefined as string[] | undefined,
  onMoveEnd: undefined as undefined | ((viewport: GraphViewport) => void),
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
  vaultCanvasArgs: vi.fn(),
  canvas: {
    data: undefined as VaultCanvasDocument | undefined,
    isLoading: false,
    isError: false,
    error: null as Error | null,
    refetch: vi.fn(),
  },
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
  useVaultCanvas: (vaultId?: string, relativePath?: string, enabled?: boolean) => {
    queries.vaultCanvasArgs(vaultId, relativePath, enabled)
    return queries.canvas
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
    onMarkdownChange,
    graphViewport,
    onGraphViewportChange,
  }: {
    mode: string
    onReload: () => Promise<unknown>
    onNavigate: (noteId: string) => void
    onMarkdownChange?: (markdown: string) => void
    graphViewport?: GraphViewport
    onGraphViewportChange?: (viewport: GraphViewport) => void
  }) => {
    overlayView.onReload = onReload
    overlayView.onNavigate = onNavigate
    overlayView.onMarkdownChange = onMarkdownChange
    overlayView.graphViewport = graphViewport
    overlayView.onGraphViewportChange = onGraphViewportChange
    useEffect(() => {
      if (overlayView.restoredMarkdown !== undefined) {
        onMarkdownChange?.(overlayView.restoredMarkdown)
      }
    }, [onMarkdownChange])
    return <section aria-label={`Overlay document ${mode}`} />
  },
}))

vi.mock('./DocumentMetricsFooter', () => ({
  DocumentMetricsFooter: ({
    text,
    selectionText,
    visible,
    hasDocument,
    emptyLabel,
  }: {
    text: string
    selectionText: string
    visible: boolean
    hasDocument: boolean
    emptyLabel: string
  }) => {
    metricFooter.props = { text, selectionText, visible, hasDocument, emptyLabel }
    if (!visible) return null
    return <footer role="status">{hasDocument ? text : emptyLabel}</footer>
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
  VaultGraph: ({
    viewport,
    relationKinds,
    rootDocumentId,
    spaceIds,
    onMoveEnd,
  }: {
    viewport?: GraphViewport
    relationKinds?: string[]
    rootDocumentId?: string | null
    spaceIds?: string[]
    onMoveEnd?: (viewport: GraphViewport) => void
  }) => {
    vaultGraphView.viewport = viewport
    vaultGraphView.relationKinds = relationKinds
    vaultGraphView.rootDocumentId = rootDocumentId
    vaultGraphView.spaceIds = spaceIds
    vaultGraphView.onMoveEnd = onMoveEnd
    return <div>Local graph content</div>
  },
}))

vi.mock('./KnowledgeAskPane', () => ({
  KnowledgeAskPane: ({ readinessReason }: { readinessReason?: string | null }) => (
    <div>Ask shell {readinessReason ?? 'ready'}</div>
  ),
}))

vi.mock('./KnowledgeSearchPane', () => ({
  KnowledgeSearchPane: () => <div>Search shell</div>,
}))

vi.mock('./KnowledgePodcastPane', () => ({
  KnowledgePodcastPane: () => <div>Podcast shell</div>,
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

const canvasFixture: VaultCanvasDocument = {
  file: {
    ...pageFixture.file,
    id: 'file:canvas',
    note_id: 'note:canvas',
    relative_path: 'maps/Plan.canvas',
    file_kind: 'metadata',
  },
  source_hash: 'b'.repeat(64),
  nodes: [{
    id: 'idea', type: 'text', x: 0, y: 0, width: 100, height: 80,
    text: 'Idea', file_path: null, label: null,
  }],
  edges: [],
}

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

function replaceWorkspace(viewMode: 'reading' | 'source' | 'live-preview' | 'graph' | 'canvas' = 'reading') {
  useKnowledgeWorkspaceStore.getState().replaceWorkspace(parseKnowledgeWorkspace(serializeKnowledgeWorkspace({
    version: 2,
    activePaneId: 'pane-1',
    nextId: 2,
    panes: {
      'pane-1': {
        id: 'pane-1',
        activeTabId: 'tab-1',
        tabs: [{
          id: 'tab-1',
          vaultId: 'vault:one',
          noteId: viewMode === 'canvas' ? 'note:canvas' : 'note:plan',
          title: viewMode === 'canvas' ? 'Canvas Plan' : 'Stale Plan',
          relativePath: viewMode === 'canvas' ? 'maps/Plan.canvas' : 'synthetic/stale.md',
          viewMode,
          sourceAuthority: 'external-vault',
          knowledgeDocumentId: null,
          graphViewport: { x: 0, y: 0, zoom: 1 },
        }],
      },
    },
    layout: { type: 'pane', paneId: 'pane-1' },
    navigation: useKnowledgeWorkspaceStore.getState().navigation,
  })))
}

function replaceOverlayWorkspace(
  viewMode: 'reading' | 'source' | 'live-preview' | 'graph' = 'source',
) {
  useKnowledgeWorkspaceStore.getState().replaceWorkspace(parseKnowledgeWorkspace(serializeKnowledgeWorkspace({
    version: 2,
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
          knowledgeDocumentId: null,
          graphViewport: { x: 0, y: 0, zoom: 1 },
        }],
      },
    },
    layout: { type: 'pane', paneId: 'pane-1' },
    navigation: useKnowledgeWorkspaceStore.getState().navigation,
  })))
}

function replaceResearchWorkspace(
  mode: 'ask' | 'graph' | 'podcast',
) {
  const documentTarget = {
    kind: 'document' as const,
    container_id: 'vault:one',
    note_id: 'note:plan',
    title: 'Canonical Plan',
    relative_locator: 'pages/plan.md',
    authority: 'external-vault' as const,
    knowledge_document_id: 'knowledge_engine_document:plan',
    render_mode: 'reading' as const,
  }
  const target = mode === 'ask'
    ? { kind: 'ask' as const, thread_id: null, selected_document_ids: [] }
    : mode === 'graph'
        ? {
            kind: 'graph' as const,
            root_document_id: 'knowledge_engine_document:plan',
            space_ids: ['knowledge_engine_space:target'],
            relation_kinds: ['target-link'],
            viewport: { x: 0, y: 0, zoom: 1 },
            origin: documentTarget,
          }
        : { kind: 'podcast' as const, production_id: null, seed_document_ids: ['knowledge_engine_document:plan'] }
  useKnowledgeWorkspaceStore.getState().replaceWorkspace(parseKnowledgeWorkspace(serializeKnowledgeWorkspace({
    version: 2,
    activePaneId: 'pane-1',
    nextId: 2,
    panes: {
      'pane-1': {
        id: 'pane-1', activeTabId: 'tab-1', tabs: [{
          id: 'tab-1', mode, target, title: mode === 'ask' ? 'Ask' : mode === 'podcast' ? 'Podcast' : 'Canonical Plan',
          vaultId: '', noteId: '', relativePath: '', viewMode: 'reading',
          sourceAuthority: 'external-vault', knowledgeDocumentId: null, graphViewport: null,
        }],
      },
    },
    layout: { type: 'pane', paneId: 'pane-1' },
    navigation: useKnowledgeWorkspaceStore.getState().navigation,
  })))
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
  useKnowledgeWorkspaceStore.getState().replaceWorkspace(parseKnowledgeWorkspace(serializeKnowledgeWorkspace({
    version: 2,
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
          knowledgeDocumentId: null,
          graphViewport: { x: 0, y: 0, zoom: 1 },
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
          knowledgeDocumentId: null,
          graphViewport: { x: 0, y: 0, zoom: 1 },
        }],
      },
    },
    layout: {
      type: 'split',
      id: 'split-1',
      direction: 'horizontal',
      firstSize: 50,
      first: { type: 'pane', paneId: 'pane-1' },
      second: { type: 'pane', paneId: 'pane-2' },
    },
    navigation: useKnowledgeWorkspaceStore.getState().navigation,
  })))
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
    queries.vaultCanvasArgs.mockClear()
    queries.vaultPageArgs.mockClear()
    queries.vaultOutgoingArgs.mockClear()
    queries.overlayPageArgs.mockClear()
    queries.outgoingLinks = []
    queries.canvas = {
      data: canvasFixture,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }
    overlayView.onReload = undefined
    overlayView.onNavigate = undefined
    overlayView.onMarkdownChange = undefined
    overlayView.restoredMarkdown = undefined
    overlayView.graphViewport = undefined
    overlayView.onGraphViewportChange = undefined
    vaultGraphView.viewport = undefined
    vaultGraphView.relationKinds = undefined
    vaultGraphView.onMoveEnd = undefined
    vaultMarkdownView.onNavigate = undefined
    metricFooter.props = undefined
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

  it('dispatches Ask and Podcast targets without document queries', () => {
    replaceResearchWorkspace('ask')
    const { rerender } = renderPane()

    expect(screen.getByText('Ask shell ready')).toBeInTheDocument()
    expect(queries.vaultPageArgs).toHaveBeenLastCalledWith(undefined, undefined)

    replaceResearchWorkspace('podcast')
    rerender(<PaneHarness />)

    expect(screen.getByText('Podcast shell')).toBeInTheDocument()
    expect(queries.vaultPageArgs).toHaveBeenLastCalledWith(undefined, undefined)
  })

  it('dispatches a restored graph target through its document origin', () => {
    replaceResearchWorkspace('graph')

    renderPane()

    expect(queries.graph).toHaveBeenLastCalledWith('vault:one', 'note:plan', true)
    expect(screen.getByText('Local graph content')).toBeInTheDocument()
  })

  it('keeps persisted graph filters ahead of a same-root global graph context', () => {
    replaceResearchWorkspace('graph')
    useKnowledgeWorkspaceStore.getState().setGraphBookmarkContext({
      rootDocumentId: 'knowledge_engine_document:plan',
      spaceIds: ['knowledge_engine_space:global'],
      relationKinds: ['global-link'],
      viewport: { x: 40, y: 40, zoom: 2 },
    })

    renderPane()

    expect(vaultGraphView.spaceIds).toEqual(['knowledge_engine_space:target'])
    expect(vaultGraphView.relationKinds).toEqual(['target-link'])
  })

  it('renders a Canvas tab without loading a Markdown page', () => {
    replaceWorkspace('canvas')

    renderPane()

    expect(screen.getByLabelText('Canvas viewer')).toBeInTheDocument()
    expect(queries.vaultCanvasArgs).toHaveBeenCalledWith(
      'vault:one',
      'maps/Plan.canvas',
      true,
    )
    expect(queries.vaultPageArgs).toHaveBeenLastCalledWith(undefined, undefined)
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

  it('renders active document metrics and accepts selection only inside its pane', () => {
    renderPane()
    const pane = screen.getByRole('region', {
      name: 'knowledge.knowledgePane modes pane-1',
    })
    const title = screen.getByRole('heading', { name: 'Canonical Plan' })
    const titleText = title.firstChild
    const outside = document.createElement('p')
    outside.textContent = 'outside pane'
    document.body.append(outside)

    try {
      const selection = window.getSelection()!
      const insideRange = document.createRange()
      insideRange.selectNodeContents(title)
      selection.removeAllRanges()
      selection.addRange(insideRange)
      fireEvent(document, new Event('selectionchange'))

      expect(within(pane).getByRole('status')).toBeInTheDocument()
      expect(metricFooter.props).toMatchObject({
        text: '# Plan',
        selectionText: 'Canonical Plan',
      })

      const outsideRange = document.createRange()
      outsideRange.setStart(titleText!, 0)
      outsideRange.setEnd(outside.firstChild!, outside.textContent!.length)
      selection.removeAllRanges()
      selection.addRange(outsideRange)
      fireEvent(document, new Event('selectionchange'))

      expect(metricFooter.props?.selectionText).toBe('')
    } finally {
      window.getSelection()?.removeAllRanges()
      outside.remove()
    }
  })

  it('persists an external controlled graph viewport and restores it after serialization', () => {
    replaceWorkspace('graph')
    queries.page.data = { ...pageFixture, knowledge_document_id: 'knowledge_engine_document:plan' }
    const original = useKnowledgeWorkspaceStore.getState()
    const tabId = original.panes['pane-1'].activeTabId!
    original.setTabGraphViewport('pane-1', tabId, { x: 12, y: -4, zoom: 1.5 })
    original.reconcileTabReference('pane-1', tabId, {
      title: 'Canonical Plan', relativePath: 'pages/plan.md',
      knowledgeDocumentId: 'knowledge_engine_document:plan',
    })
    original.setGraphBookmarkContext({
      rootDocumentId: 'knowledge_engine_document:plan',
      spaceIds: ['knowledge_engine_space:research'],
      relationKinds: ['wikilink'],
      viewport: { x: 12, y: -4, zoom: 1.5 },
    })
    const { rerender } = renderPane()

    expect(vaultGraphView.viewport).toEqual({ x: 12, y: -4, zoom: 1.5 })
    expect(vaultGraphView.relationKinds).toEqual(['wikilink'])
    act(() => vaultGraphView.onMoveEnd?.({ x: 20, y: 10, zoom: 2 }))
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0].graphViewport)
      .toEqual({ x: 20, y: 10, zoom: 2 })

    const restored = parseKnowledgeWorkspace(
      serializeKnowledgeWorkspace(useKnowledgeWorkspaceStore.getState()),
    )
    useKnowledgeWorkspaceStore.getState().replaceWorkspace(restored)
    rerender(<PaneHarness />)
    expect(vaultGraphView.viewport).toEqual({ x: 20, y: 10, zoom: 2 })
  })

  it('renders a restored graph tab with its saved root and spaces instead of global navigation filters', () => {
    replaceWorkspace('graph')
    const state = useKnowledgeWorkspaceStore.getState()
    const tabId = state.panes['pane-1'].activeTabId!
    state.reconcileTabReference('pane-1', tabId, {
      title: 'Canonical Plan', relativePath: 'pages/plan.md',
      knowledgeDocumentId: 'knowledge_engine_document:plan',
    })
    state.setNavigation({ selectedSpaceIds: ['knowledge_engine_space:global'] })
    state.setTabGraphViewport('pane-1', tabId, { x: 7, y: -3, zoom: 1.25 })
    useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0].graphBookmarkContext = {
      rootDocumentId: 'knowledge_engine_document:restored-root',
      spaceIds: ['knowledge_engine_space:restored'], relationKinds: ['embed'],
      viewport: { x: 7, y: -3, zoom: 1.25 },
    }

    renderPane()

    expect(vaultGraphView.rootDocumentId).toBe('knowledge_engine_document:restored-root')
    expect(vaultGraphView.spaceIds).toEqual(['knowledge_engine_space:restored'])
    expect(vaultGraphView.relationKinds).toEqual(['embed'])
    expect(vaultGraphView.viewport).toEqual({ x: 7, y: -3, zoom: 1.25 })
  })

  it('persists an overlay controlled graph viewport through the workspace store', () => {
    replaceOverlayWorkspace('graph')
    queries.overlayPage = {
      data: overlayGraphPage(), isLoading: false, isError: false, error: null, refetch: vi.fn(),
    }
    renderPane()

    expect(overlayView.graphViewport).toEqual({ x: 0, y: 0, zoom: 1 })
    act(() => overlayView.onGraphViewportChange?.({ x: -8, y: 16, zoom: 0.75 }))

    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs[0].graphViewport)
      .toEqual({ x: -8, y: 16, zoom: 0.75 })
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

  it('uses the overlay draft callback as the active metrics buffer', () => {
    replaceOverlayWorkspace('source')
    queries.overlayPage = {
      data: overlayPageWithTarget('overlay_note:target'),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }

    renderPane()
    expect(metricFooter.props?.text).toBe('# Research\n')

    act(() => overlayView.onMarkdownChange?.('🧠'))
    expect(metricFooter.props?.text).toBe('🧠')
  })

  it.each(['reading', 'source', 'live-preview', 'graph'] as const)(
    'keeps a restored overlay draft as the metrics buffer in %s mode',
    async (mode) => {
      replaceOverlayWorkspace(mode)
      queries.overlayPage = {
        data: overlayPageWithTarget('overlay_note:target'),
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      }

      overlayView.restoredMarkdown = 'restored 🧠 draft'
      renderPane()

      await waitFor(() => expect(metricFooter.props?.text).toBe('restored 🧠 draft'))
    },
  )

  it('keeps an empty metrics footer for a loaded rootless global graph', () => {
    replaceWorkspace('graph')
    queries.page = {
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    }

    renderPane()

    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText('knowledge.selectNote')).toBeInTheDocument()
    expect(metricFooter.props).toMatchObject({
      text: '',
      hasDocument: false,
      visible: true,
    })
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

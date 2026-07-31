import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { OverlayPage } from '@/lib/api/overlay'
import type { GraphViewport } from '@/lib/api/knowledge-workspace'
import {
  resetOverlayDraftStore,
  useOverlayDraftStore,
} from '@/lib/stores/overlay-draft-store'

const overlayMutation = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
}))
const linkViews = vi.hoisted(() => ({
  markdown: [] as Array<{ id: string; resolved: boolean }>,
  livePreview: [] as Array<{ id: string; resolved: boolean }>,
  graphUnresolved: [] as Array<{ id: string; resolved: boolean }>,
  outgoing: [] as Array<{ id: string; resolved: boolean }>,
  backlinks: [] as Array<{ id: string; resolved: boolean }>,
  graphViewport: undefined as GraphViewport | undefined,
  graphMoveEnd: undefined as undefined | ((viewport: GraphViewport) => void),
}))

vi.mock('@/lib/hooks/use-overlay', () => ({
  useUpdateOverlayNote: () => overlayMutation,
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, string | number>) => {
      const copy: Record<string, string> = {
        'common.cancel': 'Cancel',
        'common.title': 'Title',
        'knowledge.overlay.save': 'Save',
        'knowledge.overlay.saving': 'Saving…',
        'knowledge.overlay.saved': 'Saved',
        'knowledge.overlay.dirtyDraft': 'Unsaved draft',
        'knowledge.overlay.revision': `Revision ${options?.revision}`,
        'knowledge.overlay.projectionCurrent': 'Projection current',
        'knowledge.overlay.projectionPending': 'Projection pending',
        'knowledge.overlay.projectionFailed': 'Projection failed',
        'knowledge.overlay.projectionConflict': 'Projection conflict',
        'knowledge.overlay.writable': 'Writable app-owned note',
        'knowledge.overlay.saveError': 'The draft could not be saved.',
        'knowledge.overlay.conflict': 'This note changed elsewhere. Your draft is still safe.',
        'knowledge.overlay.reload': 'Review server version',
        'knowledge.overlay.reloadTitle': 'Discard local draft?',
        'knowledge.overlay.reloadDescription': 'Reload the latest server revision and discard this local draft.',
        'knowledge.overlay.discardAndReload': 'Discard and reload',
        'knowledge.overlay.reloadError': 'The server revision could not be reloaded.',
        'knowledge.source': 'Source',
        'knowledge.reader': 'Reader',
        'knowledge.livePreview': 'Live Preview',
        'knowledge.localGraph': 'Local graph',
        'knowledge.footnotes': 'Footnotes',
        'knowledge.noProperties': 'No properties.',
        'knowledge.noTags': 'No tags.',
        'knowledge.outline': 'Outline',
        'knowledge.properties': 'Properties',
        'knowledge.tags': 'Tags',
        'knowledge.outgoing': 'Outgoing links',
        'knowledge.backlinks': 'Backlinks',
        'knowledge.unresolved': 'Unresolved link',
        'knowledge.overlay.noteDetails': 'Note details',
        'knowledge.overlay.noHeadings': 'No headings',
      }
      return copy[key] ?? key
    },
  }),
}))

vi.mock('./OverlaySourceEditor', () => ({
  OverlaySourceEditor: ({
    ariaLabel,
    markdown,
    onChange,
    disabled,
  }: {
    ariaLabel: string
    markdown: string
    onChange: (markdown: string) => void
    disabled?: boolean
  }) => (
    <textarea
      aria-label={ariaLabel}
      value={markdown}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))

vi.mock('@/components/vault/VaultMarkdown', () => ({
  VaultMarkdown: ({
    markdown,
    links,
  }: {
    markdown: string
    links: Array<{ id: string; resolved: boolean }>
  }) => {
    linkViews.markdown = links
    return <div data-testid="overlay-reading">{markdown}</div>
  },
}))

vi.mock('@/components/vault/VaultLivePreview', () => ({
  VaultLivePreview: ({
    markdown,
    links,
  }: {
    markdown: string
    links: Array<{ id: string; resolved: boolean }>
  }) => {
    linkViews.livePreview = links
    return <div data-testid="overlay-live-preview">{markdown}</div>
  },
}))

vi.mock('@/components/vault/VaultGraph', () => ({
  VaultGraph: ({
    unresolved,
    viewport,
    onMoveEnd,
  }: {
    unresolved: Array<{ id: string; resolved: boolean }>
    viewport?: GraphViewport
    onMoveEnd?: (viewport: GraphViewport) => void
  }) => {
    linkViews.graphUnresolved = unresolved
    linkViews.graphViewport = viewport
    linkViews.graphMoveEnd = onMoveEnd
    return <div data-testid="overlay-graph" />
  },
}))

vi.mock('@/components/vault/VaultLinks', () => ({
  VaultLinks: ({
    title,
    direction,
    links,
  }: {
    title: string
    direction: 'source' | 'target'
    links: Array<{ id: string; resolved: boolean }>
  }) => {
    linkViews[direction === 'source' ? 'backlinks' : 'outgoing'] = links
    return <div>{title}</div>
  },
}))

import { OverlayDocumentView } from './OverlayDocumentView'

function pageAt(
  revision: number,
  markdown = '# Research\n',
  contentHash = 'a'.repeat(64),
): OverlayPage {
  return {
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
      content_hash: contentHash,
      revision,
      projection_state: 'current',
      encoding: 'utf-8',
      newline: 'lf',
      created_at: '2026-07-29T12:00:00+00:00',
      updated_at: '2026-07-29T12:00:00+00:00',
    },
    editable_markdown: markdown,
    note: {
      id: 'note:research',
      title: 'Research',
      content: `---\ntitle: Research\ndeeper_notebook:\n  id: overlay_note:research\n---\n${markdown}`,
      properties: { status: 'active' },
      tags: ['research'],
    },
    blocks: [],
    tasks: [],
    outgoing_links: [],
    backlinks: [],
    graph: { nodes: [], edges: [] },
  }
}

function editMarkdown(markdown: string) {
  fireEvent.change(screen.getByRole('textbox', { name: 'Research source' }), {
    target: { value: markdown },
  })
}

describe('OverlayDocumentView', () => {
  beforeEach(() => {
    resetOverlayDraftStore()
    overlayMutation.mutateAsync.mockReset()
    linkViews.markdown = []
    linkViews.livePreview = []
    linkViews.graphUnresolved = []
    linkViews.outgoing = []
    linkViews.backlinks = []
  })

  it('saves with the loaded revision and adopts only the successful page', async () => {
    let resolveSave!: (page: OverlayPage) => void
    overlayMutation.mutateAsync.mockReturnValue(new Promise((resolve) => {
      resolveSave = resolve
    }))
    render(
      <OverlayDocumentView
        viewId="pane-1:tab-1"
        page={pageAt(3)}
        mode="source"
        onNavigate={vi.fn()}
      />,
    )

    expect(screen.getByRole('textbox', { name: 'Research source' }))
      .toHaveValue('# Research\n')
    editMarkdown('# Changed\n')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(overlayMutation.mutateAsync).toHaveBeenCalledWith({
      id: 'overlay_note:research',
      title: 'Research',
      markdown: '# Changed\n',
      expectedRevision: 3,
      idempotencyKey: expect.stringMatching(/^save-/),
    })
    expect(screen.getByText('Revision 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled()

    resolveSave(pageAt(4, '# Changed\n', 'b'.repeat(64)))
    expect(await screen.findByText('Revision 4')).toBeInTheDocument()
    expect(screen.getByText('Saved')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    expect(useOverlayDraftStore.getState().drafts).toEqual({})
  })

  it('restores a dirty draft after its overlay tab unmounts and remounts', () => {
    const first = render(
      <OverlayDocumentView
        viewId="pane-1:tab-7"
        page={pageAt(3)}
        mode="source"
        onNavigate={vi.fn()}
      />,
    )
    editMarkdown('# Draft survives tab switch\n')
    first.unmount()

    render(
      <OverlayDocumentView
        viewId="pane-1:tab-7"
        page={pageAt(3)}
        mode="source"
        onNavigate={vi.fn()}
      />,
    )

    expect(screen.getByRole('textbox', { name: 'Research source' }))
      .toHaveValue('# Draft survives tab switch\n')
    expect(screen.getByText('Unsaved draft')).toBeInTheDocument()
  })

  it('reports markdown changes and retains a dirty draft during server updates', () => {
    const onMarkdownChange = vi.fn()
    const { rerender } = render(
      <OverlayDocumentView
        page={pageAt(3)}
        mode="source"
        onNavigate={vi.fn()}
        onMarkdownChange={onMarkdownChange}
      />,
    )

    editMarkdown('# Local draft\n')
    expect(onMarkdownChange).toHaveBeenLastCalledWith('# Local draft\n')

    rerender(
      <OverlayDocumentView
        page={pageAt(4, '# Server update\n', 'b'.repeat(64))}
        mode="source"
        onNavigate={vi.fn()}
        onMarkdownChange={onMarkdownChange}
      />,
    )

    expect(onMarkdownChange).toHaveBeenLastCalledWith('# Local draft\n')
  })

  it('reports an adopted clean server page to its owner', () => {
    const onMarkdownChange = vi.fn()
    const { rerender } = render(
      <OverlayDocumentView
        page={pageAt(3)}
        mode="source"
        onNavigate={vi.fn()}
        onMarkdownChange={onMarkdownChange}
      />,
    )

    rerender(
      <OverlayDocumentView
        page={pageAt(4, '# Server update\n', 'b'.repeat(64))}
        mode="source"
        onNavigate={vi.fn()}
        onMarkdownChange={onMarkdownChange}
      />,
    )

    expect(onMarkdownChange).toHaveBeenLastCalledWith('# Server update\n')
  })

  it('uses a new idempotency key for each explicit failed save attempt', async () => {
    overlayMutation.mutateAsync.mockRejectedValue(new Error('offline'))
    render(
      <OverlayDocumentView
        page={pageAt(3)}
        mode="source"
        onNavigate={vi.fn()}
      />,
    )
    editMarkdown('# Local draft\n')

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(overlayMutation.mutateAsync).toHaveBeenCalledTimes(2))

    const firstKey = overlayMutation.mutateAsync.mock.calls[0][0].idempotencyKey
    const secondKey = overlayMutation.mutateAsync.mock.calls[1][0].idempotencyKey
    expect(secondKey).not.toBe(firstKey)
    expect(screen.getByRole('textbox', { name: 'Research source' }))
      .toHaveValue('# Local draft\n')
  })

  it('resets a clean draft from server updates but preserves a dirty draft', () => {
    const { rerender } = render(
      <OverlayDocumentView
        page={pageAt(3)}
        mode="source"
        onNavigate={vi.fn()}
      />,
    )

    rerender(
      <OverlayDocumentView
        page={pageAt(4, '# Server update\n', 'b'.repeat(64))}
        mode="source"
        onNavigate={vi.fn()}
      />,
    )
    expect(screen.getByRole('textbox', { name: 'Research source' }))
      .toHaveValue('# Server update\n')

    editMarkdown('# Local draft\n')
    rerender(
      <OverlayDocumentView
        page={pageAt(5, '# Newer server update\n', 'c'.repeat(64))}
        mode="source"
        onNavigate={vi.fn()}
      />,
    )
    expect(screen.getByRole('textbox', { name: 'Research source' }))
      .toHaveValue('# Local draft\n')
    expect(screen.getByText('Revision 4')).toBeInTheDocument()
  })

  it('keeps a conflicting draft and reloads only after accessible confirmation', async () => {
    overlayMutation.mutateAsync.mockRejectedValue({
      response: { status: 409, data: { detail: { code: 'overlay_revision_conflict' } } },
    })
    const onReload = vi.fn().mockResolvedValue(
      pageAt(4, '# Server version\n', 'b'.repeat(64)),
    )
    render(
      <OverlayDocumentView
        page={pageAt(3)}
        mode="source"
        onNavigate={vi.fn()}
        onReload={onReload}
      />,
    )
    editMarkdown('# Local draft\n')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('changed elsewhere')
    expect(overlayMutation.mutateAsync).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('textbox', { name: 'Research source' }))
      .toHaveValue('# Local draft\n')

    const reviewButton = screen.getByRole('button', {
      name: 'Review server version',
    })
    reviewButton.focus()
    fireEvent.click(reviewButton)
    expect(screen.getByRole('alertdialog', { name: 'Discard local draft?' }))
      .toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('textbox', { name: 'Research source' }))
      .toHaveValue('# Local draft\n')
    await waitFor(() => expect(reviewButton).toHaveFocus())

    fireEvent.click(reviewButton)
    fireEvent.click(screen.getByRole('button', { name: 'Discard and reload' }))
    await waitFor(() => expect(onReload).toHaveBeenCalledOnce())
    expect(await screen.findByRole('textbox', { name: 'Research source' }))
      .toHaveValue('# Server version\n')
    expect(screen.getByText('Revision 4')).toBeInTheDocument()
    expect(overlayMutation.mutateAsync).toHaveBeenCalledTimes(1)
  })

  it('keeps the conflict and draft when reload resolves without a fresh page', async () => {
    overlayMutation.mutateAsync.mockRejectedValue({
      response: { status: 409, data: { detail: { code: 'overlay_revision_conflict' } } },
    })
    const onReload = vi.fn().mockResolvedValue(undefined)
    render(
      <OverlayDocumentView
        page={pageAt(3)}
        mode="source"
        onNavigate={vi.fn()}
        onReload={onReload}
      />,
    )
    editMarkdown('# Local draft\n')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByText(/changed elsewhere/i)

    fireEvent.click(screen.getByRole('button', {
      name: 'Review server version',
    }))
    fireEvent.click(screen.getByRole('button', { name: 'Discard and reload' }))

    await waitFor(() => expect(onReload).toHaveBeenCalledOnce())
    expect(screen.getByRole('textbox', { name: 'Research source' }))
      .toHaveValue('# Local draft\n')
    expect(screen.getByText('Revision 3')).toBeInTheDocument()
    expect(screen.getByText(/changed elsewhere/i)).toBeInTheDocument()
    expect(screen.getByText('The server revision could not be reloaded.'))
      .toBeInTheDocument()
  })

  it('reuses pure renderers for overlay reading, live preview, and graph modes', () => {
    const { rerender } = render(
      <OverlayDocumentView
        page={pageAt(3)}
        mode="reading"
        onNavigate={vi.fn()}
      />,
    )
    expect(screen.getByTestId('overlay-reading')).toHaveTextContent('# Research')

    rerender(
      <OverlayDocumentView
        page={pageAt(3)}
        mode="live-preview"
        onNavigate={vi.fn()}
      />,
    )
    expect(screen.getByTestId('overlay-live-preview')).toBeInTheDocument()

    rerender(
      <OverlayDocumentView
        page={pageAt(3)}
        mode="graph"
        onNavigate={vi.fn()}
      />,
    )
    expect(screen.getByTestId('overlay-graph')).toBeInTheDocument()
  })

  it('forwards a controlled graph viewport and reports move-end changes', () => {
    const onGraphViewportChange = vi.fn()
    render(
      <OverlayDocumentView
        page={pageAt(3)}
        mode="graph"
        onNavigate={vi.fn()}
        workspacePaneId="pane-1"
        workspaceTabId="tab-1"
        graphViewport={{ x: 4, y: 8, zoom: 1.25 }}
        onGraphViewportChange={onGraphViewportChange}
      />,
    )

    expect(linkViews.graphViewport).toEqual({ x: 4, y: 8, zoom: 1.25 })
    act(() => linkViews.graphMoveEnd?.({ x: 9, y: -3, zoom: 2 }))
    expect(onGraphViewportChange).toHaveBeenCalledWith({ x: 9, y: -3, zoom: 2 })
  })

  it('presents null-mapped overlay links as non-navigable in every overlay view', () => {
    const page = pageAt(3)
    page.outgoing_links = [
      {
        id: 'note_link:mapped',
        source_note_id: 'note:research',
        source_overlay_note_id: 'overlay_note:research',
        source_relative_path: 'Notes/20260729-1542 Research.md',
        target_note_id: 'note:target',
        target_overlay_note_id: 'overlay_note:target',
        target_note_title: 'Target',
        target_relative_path: 'Notes/20260729-1543 Target.md',
        target_text: 'Target',
        link_kind: 'wikilink',
        resolved: true,
        source_start: 0,
        source_end: 6,
      },
      {
        id: 'note_link:external',
        source_note_id: 'note:research',
        source_overlay_note_id: 'overlay_note:research',
        source_relative_path: 'Notes/20260729-1542 Research.md',
        target_note_id: 'note:external',
        target_overlay_note_id: null,
        target_note_title: 'External',
        target_relative_path: 'External.md',
        target_text: 'External',
        link_kind: 'wikilink',
        resolved: true,
        source_start: 7,
        source_end: 15,
      },
    ]
    page.backlinks = [
      {
        ...page.outgoing_links[0],
        id: 'note_link:incoming',
        source_note_id: 'note:source',
        source_overlay_note_id: 'overlay_note:source',
        source_relative_path: 'Notes/20260729-1541 Source.md',
        target_note_id: 'note:research',
        target_overlay_note_id: 'overlay_note:research',
        target_note_title: 'Research',
        target_relative_path: 'Notes/20260729-1542 Research.md',
      },
      {
        ...page.outgoing_links[0],
        id: 'note_link:external-source',
        source_note_id: 'note:external',
        source_overlay_note_id: null,
        source_relative_path: null,
        target_note_id: 'note:research',
        target_overlay_note_id: 'overlay_note:research',
        target_note_title: 'Research',
        target_relative_path: 'Notes/20260729-1542 Research.md',
      },
    ]
    const onNavigate = vi.fn()
    const { rerender } = render(
      <OverlayDocumentView
        page={page}
        mode="reading"
        onNavigate={onNavigate}
      />,
    )

    expect(linkViews.markdown.map((link) => [link.id, link.resolved])).toEqual([
      ['note_link:mapped', true],
      ['note_link:external', false],
    ])
    expect(linkViews.outgoing).toEqual(linkViews.markdown)
    expect(linkViews.backlinks.map((link) => [link.id, link.resolved])).toEqual([
      ['note_link:incoming', true],
      ['note_link:external-source', false],
    ])

    rerender(
      <OverlayDocumentView
        page={page}
        mode="live-preview"
        onNavigate={onNavigate}
      />,
    )
    expect(linkViews.livePreview).toEqual(linkViews.markdown)

    rerender(
      <OverlayDocumentView
        page={page}
        mode="graph"
        onNavigate={onNavigate}
      />,
    )
    expect(linkViews.graphUnresolved.map((link) => link.id))
      .toContain('note_link:external')
  })
})

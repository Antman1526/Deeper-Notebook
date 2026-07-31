import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'

const queries = vi.hoisted(() => ({
  overlayPage: vi.fn(),
  vaultPage: vi.fn(),
  vaultBacklinks: vi.fn(),
  vaultOutgoing: vi.fn(),
}))

const overlayPage = {
  overlay: {
    id: 'overlay_note:source',
    source_authority: 'overlay' as const,
    space_id: 'overlay_space:default',
    projected_note_id: 'note:source',
    stable_id: 'stable-overlay-source',
    kind: 'unique' as const,
    date_key: null,
    relative_path: 'Notes/20260729-1542 Source.md',
    title: 'Source',
    content_hash: 'a'.repeat(64),
    revision: 1,
    projection_state: 'current' as const,
    encoding: 'utf-8' as const,
    newline: 'lf' as const,
    created_at: '2026-07-29T12:00:00+00:00',
    updated_at: '2026-07-29T12:00:00+00:00',
  },
  editable_markdown: '# Source\n',
  note: { id: 'note:source', title: 'Source', markdown: '# Source\n' },
  blocks: [],
  tasks: [],
  outgoing_links: [{
    id: 'link:overlay',
    source_note_id: 'note:source',
    source_overlay_note_id: 'overlay_note:source',
    source_relative_path: 'Notes/20260729-1542 Source.md',
    target_note_id: 'note:target',
    target_overlay_note_id: 'overlay_note:target' as string | null,
    target_note_title: 'Target',
    target_relative_path: 'Notes/20260729-1543 Target.md',
    target_text: 'Target',
    link_kind: 'wikilink',
    resolved: true,
    source_start: 0,
    source_end: 8,
  }],
  backlinks: [{
    id: 'link:backlink',
    source_note_id: 'note:backlink',
    source_overlay_note_id: 'overlay_note:backlink',
    source_relative_path: 'Notes/20260729-1541 Backlink.md',
    source_note_title: 'Backlink',
    target_note_id: 'note:source',
    target_overlay_note_id: 'overlay_note:source',
    target_note_title: 'Source',
    target_relative_path: 'Notes/20260729-1542 Source.md',
    target_text: 'Source',
    link_kind: 'wikilink',
    resolved: true,
    source_start: 0,
    source_end: 8,
  }],
  graph: null,
}

let currentOverlayPage = overlayPage

vi.mock('@/lib/hooks/use-overlay', () => ({
  useOverlayPage: (noteId?: string) => {
    queries.overlayPage(noteId)
    return {
      data: noteId ? currentOverlayPage : undefined,
      isLoading: false,
      isError: false,
    }
  },
}))

vi.mock('@/lib/hooks/use-vault', () => ({
  useVaultPage: (vaultId?: string, noteId?: string) => {
    queries.vaultPage(vaultId, noteId)
    return { data: undefined, isLoading: false, isError: false }
  },
  useVaultBacklinks: (vaultId?: string, noteId?: string) => {
    queries.vaultBacklinks(vaultId, noteId)
    return { data: undefined, isLoading: false, isError: false }
  },
  useVaultOutgoing: (vaultId?: string, noteId?: string) => {
    queries.vaultOutgoing(vaultId, noteId)
    return { data: undefined, isLoading: false, isError: false }
  },
}))

import { KnowledgeLinksInspector } from './KnowledgeLinksInspector'

describe('KnowledgeLinksInspector authority routing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentOverlayPage = overlayPage
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
            noteId: 'overlay_note:source',
            title: 'Source',
            relativePath: 'Notes/20260729-1542 Source.md',
            viewMode: 'source',
            sourceAuthority: 'overlay',
            knowledgeDocumentId: null,
            graphViewport: { x: 0, y: 0, zoom: 1 },
          }],
        },
      },
      layout: { type: 'pane', paneId: 'pane-1' },
      navigation: useKnowledgeWorkspaceStore.getState().navigation,
    })
  })

  it('uses overlay-owned links without enabling any vault query path', () => {
    const onNavigate = vi.fn()
    render(<KnowledgeLinksInspector onNavigate={onNavigate} />)

    expect(queries.overlayPage).toHaveBeenLastCalledWith('overlay_note:source')
    expect(queries.vaultPage).toHaveBeenLastCalledWith(undefined, undefined)
    expect(queries.vaultBacklinks).toHaveBeenLastCalledWith(undefined, undefined)
    expect(queries.vaultOutgoing).toHaveBeenLastCalledWith(undefined, undefined)

    fireEvent.click(screen.getByRole('button', { name: 'Target' }))
    expect(onNavigate).toHaveBeenCalledWith(
      'overlay_space:default',
      'overlay_note:target',
      'Notes/20260729-1543 Target.md',
      'Target',
      undefined,
      'Target',
      'overlay',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Backlink' }))
    expect(onNavigate).toHaveBeenLastCalledWith(
      'overlay_space:default',
      'overlay_note:backlink',
      'Notes/20260729-1541 Backlink.md',
      'Backlink',
      undefined,
      undefined,
      'overlay',
    )
  })

  it('does not open an overlay tab when the explicit overlay identity is absent', () => {
    currentOverlayPage = {
      ...overlayPage,
      outgoing_links: [{
        ...overlayPage.outgoing_links[0],
        target_overlay_note_id: null,
      }],
    }
    const onNavigate = vi.fn()
    render(<KnowledgeLinksInspector onNavigate={onNavigate} />)

    expect(screen.queryByRole('button', { name: 'Target' }))
      .not.toBeInTheDocument()
    const outgoing = screen.getByRole('heading', {
      name: 'knowledge.outgoing',
    }).closest('section')
    expect(outgoing).not.toBeNull()
    expect(within(outgoing!).getByRole('list')).toHaveTextContent('Target')
    expect(onNavigate).not.toHaveBeenCalled()
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
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
    relative_path: 'Unique/source.md',
    title: 'Source',
    content_hash: 'a'.repeat(64),
    revision: 1,
    projection_state: 'current' as const,
    encoding: 'utf-8' as const,
    newline: 'lf' as const,
    created_at: '2026-07-29T12:00:00+00:00',
    updated_at: '2026-07-29T12:00:00+00:00',
  },
  note: { id: 'note:source', title: 'Source', markdown: '# Source\n' },
  blocks: [],
  tasks: [],
  outgoing_links: [{
    id: 'link:overlay',
    source_note_id: 'overlay_note:source',
    target_note_id: 'overlay_note:target',
    target_note_title: 'Target',
    target_relative_path: 'Unique/target.md',
    target_text: 'Target',
    link_kind: 'wikilink',
    resolved: true,
    source_start: 0,
    source_end: 8,
  }],
  backlinks: [],
  graph: null,
}

vi.mock('@/lib/hooks/use-overlay', () => ({
  useOverlayPage: (noteId?: string) => {
    queries.overlayPage(noteId)
    return {
      data: noteId ? overlayPage : undefined,
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

vi.mock('./VaultLinks', () => ({
  VaultLinks: ({
    title,
    links,
    direction,
    onNavigate,
  }: {
    title: string
    links: typeof overlayPage.outgoing_links
    direction: 'source' | 'target'
    onNavigate: (noteId: string) => void
  }) => (
    <section>
      <h2>{title}</h2>
      {links.map((link) => (
        <button
          key={link.id}
          type="button"
          onClick={() => onNavigate(
            direction === 'source'
              ? link.source_note_id
              : link.target_note_id!,
          )}
        >
          Open {link.target_text}
        </button>
      ))}
    </section>
  ),
}))

import { KnowledgeLinksInspector } from './KnowledgeLinksInspector'

describe('KnowledgeLinksInspector authority routing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
            relativePath: 'Unique/source.md',
            viewMode: 'source',
            sourceAuthority: 'overlay',
          }],
        },
      },
      layout: { type: 'pane', paneId: 'pane-1' },
    })
  })

  it('uses overlay-owned links without enabling any vault query path', () => {
    const onNavigate = vi.fn()
    render(<KnowledgeLinksInspector onNavigate={onNavigate} />)

    expect(queries.overlayPage).toHaveBeenLastCalledWith('overlay_note:source')
    expect(queries.vaultPage).toHaveBeenLastCalledWith(undefined, undefined)
    expect(queries.vaultBacklinks).toHaveBeenLastCalledWith(undefined, undefined)
    expect(queries.vaultOutgoing).toHaveBeenLastCalledWith(undefined, undefined)

    fireEvent.click(screen.getByRole('button', { name: 'Open Target' }))
    expect(onNavigate).toHaveBeenCalledWith(
      'overlay_space:default',
      'overlay_note:target',
      'Unique/target.md',
      'Target',
      undefined,
      'Target',
      'overlay',
    )
  })
})

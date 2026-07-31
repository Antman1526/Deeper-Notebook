import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { KnowledgeBookmark } from '@/lib/api/knowledge-navigation'
import { KnowledgeBookmarksPanel } from './KnowledgeBookmarksPanel'

const externalBookmark = (): KnowledgeBookmark => ({
  schemaVersion: 1,
  id: 'knowledge_bookmark:research',
  targetKind: 'document',
  target: { kind: 'document', documentId: 'knowledge_engine_document:research' },
  displayLabel: 'Research plan', authorityKind: 'external_read_only',
  spaceId: 'knowledge_engine_space:research', folderId: null, tags: ['plans'], position: 0,
  revision: 1, createdAt: '2026-07-31T00:00:00.000Z', updatedAt: '2026-07-31T00:00:00.000Z',
  targetState: 'available',
  targetDocument: {
    documentId: 'knowledge_engine_document:research', spaceId: 'knowledge_engine_space:research',
    authorityKind: 'external_read_only', sourceKind: 'markdown', title: 'Research plan',
    relativeLocator: 'Research/Plan.md', legacyNoteId: 'note:research', legacyContainerId: 'vault:research',
  },
})

describe('KnowledgeBookmarksPanel', () => {
  it('shows external target authority while keeping bookmark metadata editable', () => {
    render(<KnowledgeBookmarksPanel bookmarks={[externalBookmark()]} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />)

    expect(screen.getByText('External read-only')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Edit bookmark Research plan' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /edit source/i })).not.toBeInTheDocument()
  })

  it('limits a stale target to repair and deletion controls', () => {
    const stale = { ...externalBookmark(), targetState: 'stale' as const }
    render(<KnowledgeBookmarksPanel bookmarks={[stale]} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'Open Research plan' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit Target Research plan' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Edit bookmark Research plan' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete bookmark Research plan' })).toBeVisible()
  })

  it('submits a revision-checked metadata edit without touching the external source', async () => {
    const onUpdate = vi.fn(async () => undefined)
    render(<KnowledgeBookmarksPanel bookmarks={[externalBookmark()]} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onUpdate={onUpdate} onDelete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Edit bookmark Research plan' }))
    fireEvent.change(screen.getByLabelText('Bookmark label'), { target: { value: 'Reviewed plan' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save bookmark metadata' }))

    expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ id: 'knowledge_bookmark:research' }), {
      displayLabel: 'Reviewed plan', tags: ['plans'],
    })
    expect(screen.queryByRole('button', { name: /edit source/i })).not.toBeInTheDocument()
  })

  it('repairs a stale target reference and surfaces a rejected revision update', async () => {
    const onUpdate = vi.fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('revision conflict'))
    const stale = { ...externalBookmark(), targetState: 'stale' as const }
    render(<KnowledgeBookmarksPanel bookmarks={[stale]} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onUpdate={onUpdate} onDelete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Edit Target Research plan' }))
    fireEvent.change(screen.getByLabelText('Target document ID'), { target: { value: 'knowledge_engine_document:repaired' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save target repair' }))

    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith(stale, {
      target: { kind: 'document', documentId: 'knowledge_engine_document:repaired' },
    }))

    fireEvent.click(screen.getByRole('button', { name: 'Edit Target Research plan' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save target repair' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Bookmark update conflicted')
  })

  it('passes the full bookmark to the typed open dispatcher', () => {
    const onOpen = vi.fn()
    const bookmark = externalBookmark()
    render(<KnowledgeBookmarksPanel bookmarks={[bookmark]} folders={[]} onOpen={onOpen} onEdit={vi.fn()} onDelete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Open Research plan' }))
    expect(onOpen).toHaveBeenCalledWith(bookmark)
  })

  it('requires an explicit folder deletion policy before mutating the tree', () => {
    const onDeleteFolder = vi.fn()
    const folder = {
      schemaVersion: 1 as const, id: 'knowledge_bookmark_folder:plans', name: 'Plans', nameKey: 'plans',
      parentFolderId: null, position: 0, revision: 2,
      createdAt: '2026-07-31T00:00:00.000Z', updatedAt: '2026-07-31T00:00:00.000Z', children: [],
    }
    render(<KnowledgeBookmarksPanel bookmarks={[]} folders={[folder]} onOpen={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} onDeleteFolder={onDeleteFolder} />)

    fireEvent.click(screen.getByRole('button', { name: 'Delete folder' }))
    expect(screen.getByRole('region', { name: 'Confirm folder deletion' })).toHaveTextContent('Delete tree permanently removes')
    expect(onDeleteFolder).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Move children' }))
    expect(onDeleteFolder).toHaveBeenCalledWith(folder, 'move_children')
  })
})

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { KnowledgeBookmark } from '@/lib/api/knowledge-navigation'
import { KnowledgeBookmarksPanel } from './KnowledgeBookmarksPanel'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'

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
  it('opens an available bookmark through the transient podcast review state', () => {
    usePodcastStudioStore.getState().dismiss()
    const bookmark = externalBookmark()
    render(<KnowledgeBookmarksPanel bookmarks={[bookmark]} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Turn into podcast' }))

    expect(usePodcastStudioStore.getState()).toMatchObject({
      isOpen: true,
      destination: 'quick',
      selections: [{
        kind: 'knowledge_collection', collectionKind: 'bookmark', collectionId: bookmark.id,
      }],
    })
  })

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

  it('keeps available search and workspace targets openable without a document descriptor', () => {
    const onOpen = vi.fn()
    const search = { ...externalBookmark(), id: 'knowledge_bookmark:search', targetKind: 'search' as const, target: { kind: 'search' as const, query: 'plan', searchMode: 'semantic' as const, spaceIds: [], authorityKinds: [], tags: [] }, targetDocument: null }
    const workspace = { ...externalBookmark(), id: 'knowledge_bookmark:workspace', targetKind: 'workspace' as const, target: { kind: 'workspace' as const, workspaceId: 'named_knowledge_workspace:desk' }, targetDocument: null }
    render(<KnowledgeBookmarksPanel bookmarks={[search, workspace]} folders={[]} onOpen={onOpen} onEdit={vi.fn()} onDelete={vi.fn()} />)

    fireEvent.click(screen.getAllByRole('button', { name: 'Open Research plan' })[0])
    fireEvent.click(screen.getAllByRole('button', { name: 'Open Research plan' })[1])
    expect(onOpen).toHaveBeenCalledWith(search)
    expect(onOpen).toHaveBeenCalledWith(workspace)
  })

  it('exposes kind-specific repair controls for block, search, graph, and workspace targets', () => {
    const variants: KnowledgeBookmark[] = [
      { ...externalBookmark(), id: 'knowledge_bookmark:block', targetKind: 'block', target: { kind: 'block', documentId: 'knowledge_engine_document:research', blockId: 'knowledge_engine_block:one', sourceRevisionId: 'knowledge_engine_revision:one' }, targetState: 'stale' },
      { ...externalBookmark(), id: 'knowledge_bookmark:search', targetKind: 'search', target: { kind: 'search', query: 'plan', searchMode: 'text', spaceIds: [], authorityKinds: [], tags: [] }, targetState: 'stale', targetDocument: null },
      { ...externalBookmark(), id: 'knowledge_bookmark:graph', targetKind: 'graph', target: { kind: 'graph', rootDocumentId: 'knowledge_engine_document:research', spaceIds: [], relationKinds: [], viewport: { x: 0, y: 0, zoom: 1 } }, targetState: 'stale' },
      { ...externalBookmark(), id: 'knowledge_bookmark:workspace', targetKind: 'workspace', target: { kind: 'workspace', workspaceId: 'named_knowledge_workspace:desk' }, targetState: 'stale', targetDocument: null },
    ]
    render(<KnowledgeBookmarksPanel bookmarks={variants} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />)

    fireEvent.click(screen.getAllByRole('button', { name: 'Edit Target Research plan' })[0])
    expect(screen.getByLabelText('Target block ID')).toBeVisible()
    expect(screen.getByLabelText('Source revision ID')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Edit Target Research plan' })[1])
    expect(screen.getByLabelText('Search mode')).toBeVisible()
    expect(screen.getByLabelText('Search space IDs')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Edit Target Research plan' })[2])
    expect(screen.getByLabelText('Graph relation kinds')).toBeVisible()
    expect(screen.getByLabelText('Graph viewport')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Edit Target Research plan' })[3])
    expect(screen.getByLabelText('Workspace ID')).toBeVisible()
  })

  it('submits a full repaired search target rather than metadata', async () => {
    const onUpdate = vi.fn(async () => undefined)
    const search = { ...externalBookmark(), targetKind: 'search' as const, target: { kind: 'search' as const, query: 'plan', searchMode: 'text' as const, spaceIds: [], authorityKinds: [], tags: [] }, targetState: 'stale' as const, targetDocument: null }
    render(<KnowledgeBookmarksPanel bookmarks={[search]} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onUpdate={onUpdate} onDelete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Edit Target Research plan' }))
    fireEvent.change(screen.getByLabelText('Search query'), { target: { value: 'renewed plan' } })
    fireEvent.change(screen.getByLabelText('Search mode'), { target: { value: 'semantic' } })
    fireEvent.change(screen.getByLabelText('Search space IDs'), { target: { value: 'knowledge_engine_space:research' } })
    fireEvent.change(screen.getByLabelText('Search authority filters'), { target: { value: 'external_read_only' } })
    fireEvent.change(screen.getByLabelText('Search tags'), { target: { value: 'plans, repair' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save target repair' }))

    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith(search, { target: {
      kind: 'search', query: 'renewed plan', searchMode: 'semantic',
      spaceIds: ['knowledge_engine_space:research'], authorityKinds: ['external_read_only'], tags: ['plans', 'repair'],
    } }))
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
    expect(screen.getByRole('region', { name: 'Confirm folder deletion' })).toHaveTextContent('contained bookmark metadata')
    expect(onDeleteFolder).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Move children' }))
    expect(onDeleteFolder).toHaveBeenCalledWith(folder, 'move_children')
  })

  it('opens a folder collection through transient podcast review state', () => {
    usePodcastStudioStore.getState().dismiss()
    const folder = {
      schemaVersion: 1 as const, id: 'knowledge_bookmark_folder:plans', name: 'Plans', nameKey: 'plans',
      parentFolderId: null, position: 0, revision: 2,
      createdAt: '2026-07-31T00:00:00.000Z', updatedAt: '2026-07-31T00:00:00.000Z', children: [],
    }
    render(<KnowledgeBookmarksPanel bookmarks={[]} folders={[folder]} onOpen={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Turn folder into podcast' }))

    expect(usePodcastStudioStore.getState().selections).toEqual([{
      kind: 'knowledge_collection', collectionKind: 'folder', collectionId: folder.id,
    }])
  })
})

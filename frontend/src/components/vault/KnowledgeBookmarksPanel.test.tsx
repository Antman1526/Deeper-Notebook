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

    expect(screen.getByText('knowledge.navigation.externalReadOnly')).toBeVisible()
    expect(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.editBookmarkAria' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /edit source/i })).not.toBeInTheDocument()
  })

  it('limits a stale target to repair and deletion controls', () => {
    const stale = { ...externalBookmark(), targetState: 'stale' as const }
    render(<KnowledgeBookmarksPanel bookmarks={[stale]} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.open' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.editTarget' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.editBookmarkAria' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.deleteBookmarkAria' })).toBeVisible()
  })

  it('submits a revision-checked metadata edit without touching the external source', async () => {
    const onUpdate = vi.fn(async () => undefined)
    render(<KnowledgeBookmarksPanel bookmarks={[externalBookmark()]} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onUpdate={onUpdate} onDelete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.editBookmarkAria' }))
    fireEvent.change(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.bookmarkLabel'), { target: { value: 'Reviewed plan' } })
    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.saveMetadata' }))

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

    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.editTarget' }))
    fireEvent.change(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.targetDocumentId'), { target: { value: 'knowledge_engine_document:repaired' } })
    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.saveTargetRepair' }))

    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith(stale, {
      target: { kind: 'document', documentId: 'knowledge_engine_document:repaired' },
    }))

    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.editTarget' }))
    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.saveTargetRepair' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('knowledge.knowledgeBookmarksPanel.updateConflict')
  })

  it('passes the full bookmark to the typed open dispatcher', () => {
    const onOpen = vi.fn()
    const bookmark = externalBookmark()
    render(<KnowledgeBookmarksPanel bookmarks={[bookmark]} folders={[]} onOpen={onOpen} onEdit={vi.fn()} onDelete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.open' }))
    expect(onOpen).toHaveBeenCalledWith(bookmark)
  })

  it('keeps available search and workspace targets openable without a document descriptor', () => {
    const onOpen = vi.fn()
    const search = { ...externalBookmark(), id: 'knowledge_bookmark:search', targetKind: 'search' as const, target: { kind: 'search' as const, query: 'plan', searchMode: 'semantic' as const, spaceIds: [], authorityKinds: [], tags: [] }, targetDocument: null }
    const workspace = { ...externalBookmark(), id: 'knowledge_bookmark:workspace', targetKind: 'workspace' as const, target: { kind: 'workspace' as const, workspaceId: 'named_knowledge_workspace:desk' }, targetDocument: null }
    render(<KnowledgeBookmarksPanel bookmarks={[search, workspace]} folders={[]} onOpen={onOpen} onEdit={vi.fn()} onDelete={vi.fn()} />)

    fireEvent.click(screen.getAllByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.open' })[0])
    fireEvent.click(screen.getAllByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.open' })[1])
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

    fireEvent.click(screen.getAllByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.editTarget' })[0])
    expect(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.targetBlockId')).toBeVisible()
    expect(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.sourceRevisionId')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'common.cancel' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.editTarget' })[1])
    expect(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.searchMode')).toBeVisible()
    expect(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.searchSpaceIds')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'common.cancel' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.editTarget' })[2])
    expect(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.graphRelationKinds')).toBeVisible()
    expect(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.graphViewport')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'common.cancel' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.editTarget' })[3])
    expect(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.workspaceId')).toBeVisible()
  })

  it('submits a full repaired search target rather than metadata', async () => {
    const onUpdate = vi.fn(async () => undefined)
    const search = { ...externalBookmark(), targetKind: 'search' as const, target: { kind: 'search' as const, query: 'plan', searchMode: 'text' as const, spaceIds: [], authorityKinds: [], tags: [] }, targetState: 'stale' as const, targetDocument: null }
    render(<KnowledgeBookmarksPanel bookmarks={[search]} folders={[]} onOpen={vi.fn()} onEdit={vi.fn()} onUpdate={onUpdate} onDelete={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.editTarget' }))
    fireEvent.change(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.searchQuery'), { target: { value: 'renewed plan' } })
    fireEvent.change(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.searchMode'), { target: { value: 'semantic' } })
    fireEvent.change(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.searchSpaceIds'), { target: { value: 'knowledge_engine_space:research' } })
    fireEvent.change(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.searchAuthorityFilters'), { target: { value: 'external_read_only' } })
    fireEvent.change(screen.getByLabelText('knowledge.knowledgeBookmarksPanel.searchTags'), { target: { value: 'plans, repair' } })
    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.saveTargetRepair' }))

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

    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.deleteFolder' }))
    expect(screen.getByRole('region', { name: 'knowledge.knowledgeBookmarksPanel.confirmFolderDeletion' })).toHaveTextContent('knowledge.knowledgeBookmarksPanel.deleteFolderExplain')
    expect(onDeleteFolder).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.moveChildren' }))
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

    fireEvent.click(screen.getByRole('button', { name: 'knowledge.knowledgeBookmarksPanel.turnFolderIntoPodcast' }))

    expect(usePodcastStudioStore.getState().selections).toEqual([{
      kind: 'knowledge_collection', collectionKind: 'folder', collectionId: folder.id,
    }])
  })
})

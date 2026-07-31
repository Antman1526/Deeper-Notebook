import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import apiClient from './client'
import {
  knowledgeNavigationApi,
  parseBookmark,
  prepareKnowledgeNavigationCommand,
} from './knowledge-navigation'

const timestamp = '2026-07-31T00:00:00Z'
const descriptorWire = {
  document_id: 'knowledge_engine_document:one',
  space_id: 'knowledge_engine_space:research',
  authority_kind: 'external_read_only',
  source_kind: 'markdown',
  title: 'One',
  relative_locator: 'Research/One.md',
  legacy_note_id: 'note:one',
  legacy_container_id: 'vault_mount:research',
}
const plainBookmarkWire = {
  schema_version: 1,
  id: 'knowledge_bookmark:one',
  target_kind: 'document',
  target: { kind: 'document', document_id: 'knowledge_engine_document:one' },
  display_label: 'One',
  authority_kind: null,
  space_id: null,
  tags: [],
  folder_id: null,
  position: 0,
  revision: 1,
  created_at: timestamp,
  updated_at: timestamp,
}
const hydratedBookmarkWire = {
  ...plainBookmarkWire,
  target_state: 'available',
  target_document: descriptorWire,
}
const folderWire = {
  schema_version: 1,
  id: 'knowledge_bookmark_folder:research',
  name: 'Research',
  name_key: 'research',
  parent_folder_id: null,
  position: 0,
  revision: 1,
  created_at: timestamp,
  updated_at: timestamp,
  children: [],
}
interface FolderFixture extends Omit<typeof folderWire, 'children'> {
  children: FolderFixture[]
}
const navigationWire = {
  utility_mode: 'bookmarks',
  sidebar_visible: true,
  sidebar_width: 360,
  active_bookmark_folder_id: 'knowledge_bookmark_folder:research',
  bookmark_tags: ['Evidence'],
  source_tree_query: 'source',
  search_query: 'search',
  active_draft_id: 'draft-one',
  selected_space_ids: ['knowledge_engine_space:research'],
  authority_filters: ['external_read_only'],
  metrics_visible: false,
}
const snapshotWire = {
  version: 1,
  active_pane_id: 'pane-one',
  next_id: 2,
  panes: {
    'pane-one': {
      id: 'pane-one',
      active_tab_id: 'tab-one',
      tabs: [{
        id: 'tab-one',
        target: { kind: 'document', document_id: 'knowledge_engine_document:one' },
        display_label: 'One',
        view_mode: 'graph',
      }],
    },
  },
  layout: { type: 'pane', pane_id: 'pane-one' },
  navigation: navigationWire,
}
const workspaceWire = {
  schema_version: 1,
  id: 'named_knowledge_workspace:desk',
  name: 'Desk',
  name_key: 'desk',
  snapshot_version: 1,
  snapshot: snapshotWire,
  capacity_slot: 0,
  revision: 1,
  created_at: timestamp,
  updated_at: timestamp,
}
const receiptWire = {
  schema_version: 1,
  operation_id: 'operation-one',
  operation_kind: 'delete',
  entity_kind: 'bookmark',
  entity_id: 'knowledge_bookmark:one',
  payload_hash: 'a'.repeat(64),
  result_status: 'succeeded',
  result_revision: 2,
  result_code: 'deleted',
  created_at: timestamp,
  completed_at: timestamp,
}

const bookmarkCreate = {
  operationId: 'operation-create-bookmark',
  target: { kind: 'document' as const, documentId: 'knowledge_engine_document:one' },
  displayLabel: 'One',
  authorityKind: null,
  spaceId: null,
  folderId: null,
  tags: [],
  position: 0,
}

describe('knowledge navigation API contracts', () => {
  beforeEach(() => vi.resetAllMocks())

  it('rejects absolute paths and unknown target fields', () => {
    expect(() => parseBookmark({
      ...hydratedBookmarkWire,
      target: {
        kind: 'document',
        document_id: 'knowledge_engine_document:one',
        root_path: '/Users/Antman/private',
      },
    })).toThrow()
  })

  it('prepares one deeply immutable operation ID and reuses the same object', () => {
    const randomUUID = vi.spyOn(crypto, 'randomUUID')
      .mockReturnValue('11111111-1111-4111-8111-111111111111')
    const command = {
      target: {
        kind: 'search' as const,
        query: 'evidence',
        searchMode: 'text' as const,
        spaceIds: ['knowledge_engine_space:research'],
        authorityKinds: ['external_read_only' as const],
        tags: ['Evidence'],
      },
    }

    const prepared = prepareKnowledgeNavigationCommand(command)
    const retry = prepareKnowledgeNavigationCommand(prepared)

    expect(randomUUID).toHaveBeenCalledTimes(1)
    expect(retry).toBe(prepared)
    expect(prepared.operationId).toBe('11111111-1111-4111-8111-111111111111')
    expect(Object.isFrozen(prepared)).toBe(true)
    expect(Object.isFrozen(prepared.target)).toBe(true)
    expect(Object.isFrozen(prepared.target.spaceIds)).toBe(true)
    expect(command).not.toHaveProperty('operationId')
  })

  it('calls every bookmark and folder API with exact wire requests and parsed DTOs', async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { items: [hydratedBookmarkWire], next_cursor: null } } as never)
      .mockResolvedValueOnce({ data: { items: [folderWire] } } as never)
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: plainBookmarkWire } as never)
      .mockResolvedValueOnce({ data: folderWire } as never)
    vi.mocked(apiClient.patch)
      .mockResolvedValueOnce({ data: { ...plainBookmarkWire, display_label: 'Renamed' } } as never)
      .mockResolvedValueOnce({ data: { ...folderWire, name: 'Archive', name_key: 'archive' } } as never)
    vi.mocked(apiClient.delete)
      .mockResolvedValueOnce({ data: receiptWire } as never)
      .mockResolvedValueOnce({ data: { ...receiptWire, entity_kind: 'folder' } } as never)

    await expect(knowledgeNavigationApi.listBookmarks({
      cursor: 'opaque',
      limit: 20,
      folderId: 'knowledge_bookmark_folder:research',
      tags: ['Evidence'],
      targetKinds: ['document'],
      spaceIds: ['knowledge_engine_space:research'],
      authorityKinds: ['external_read_only'],
    })).resolves.toEqual({
      items: [expect.objectContaining({
        id: 'knowledge_bookmark:one',
        displayLabel: 'One',
        targetState: 'available',
        targetDocument: expect.objectContaining({ relativeLocator: 'Research/One.md' }),
      })],
      nextCursor: null,
    })
    await expect(knowledgeNavigationApi.createBookmark(bookmarkCreate))
      .resolves.toEqual(expect.objectContaining({ id: 'knowledge_bookmark:one' }))
    await knowledgeNavigationApi.updateBookmark('knowledge_bookmark:one', {
      operationId: 'operation-update-bookmark',
      expectedRevision: 1,
      displayLabel: 'Renamed',
    })
    await knowledgeNavigationApi.deleteBookmark('knowledge_bookmark:one', {
      operationId: 'operation-delete-bookmark', expectedRevision: 2,
    })
    await expect(knowledgeNavigationApi.listFolders()).resolves.toEqual({
      items: [expect.objectContaining({ nameKey: 'research', children: [] })],
    })
    await knowledgeNavigationApi.createFolder({
      operationId: 'operation-create-folder', name: 'Research',
      parentFolderId: null, position: 0,
    })
    await expect(knowledgeNavigationApi.updateFolder('knowledge_bookmark_folder:research', {
      operationId: 'operation-update-folder', expectedRevision: 1,
      name: 'Archive', parentFolderId: null, position: 1,
    })).resolves.toEqual(expect.objectContaining({ nameKey: 'archive' }))
    await knowledgeNavigationApi.deleteFolder('knowledge_bookmark_folder:research', {
      operationId: 'operation-delete-folder', expectedRevision: 2,
      childDisposition: 'delete_tree',
    })

    expect(apiClient.get).toHaveBeenNthCalledWith(1, '/deeper-notebook/knowledge/bookmarks', {
      params: {
        cursor: 'opaque', limit: 20,
        folder_id: 'knowledge_bookmark_folder:research',
        tag: ['Evidence'], target_kind: ['document'],
        space_id: ['knowledge_engine_space:research'],
        authority_kind: ['external_read_only'],
      },
    })
    expect(apiClient.get).toHaveBeenNthCalledWith(2, '/deeper-notebook/knowledge/bookmark-folders')
    expect(apiClient.post).toHaveBeenNthCalledWith(1, '/deeper-notebook/knowledge/bookmarks', {
      operation_id: 'operation-create-bookmark',
      target: { kind: 'document', document_id: 'knowledge_engine_document:one' },
      display_label: 'One', authority_kind: null, space_id: null,
      folder_id: null, tags: [], position: 0,
    })
    expect(apiClient.patch).toHaveBeenNthCalledWith(
      1,
      '/deeper-notebook/knowledge/bookmarks/knowledge_bookmark%3Aone',
      { operation_id: 'operation-update-bookmark', expected_revision: 1, display_label: 'Renamed' },
    )
    expect(apiClient.delete).toHaveBeenNthCalledWith(
      1,
      '/deeper-notebook/knowledge/bookmarks/knowledge_bookmark%3Aone',
      { data: { operation_id: 'operation-delete-bookmark', expected_revision: 2 } },
    )
    expect(apiClient.post).toHaveBeenNthCalledWith(2, '/deeper-notebook/knowledge/bookmark-folders', {
      operation_id: 'operation-create-folder', name: 'Research',
      parent_folder_id: null, position: 0,
    })
    expect(apiClient.patch).toHaveBeenNthCalledWith(
      2,
      '/deeper-notebook/knowledge/bookmark-folders/knowledge_bookmark_folder%3Aresearch',
      {
        operation_id: 'operation-update-folder', expected_revision: 1,
        name: 'Archive', parent_folder_id: null, position: 1,
      },
    )
    expect(apiClient.delete).toHaveBeenNthCalledWith(
      2,
      '/deeper-notebook/knowledge/bookmark-folders/knowledge_bookmark_folder%3Aresearch',
      { data: {
        operation_id: 'operation-delete-folder', expected_revision: 2,
        child_disposition: 'delete_tree',
      } },
    )
  })

  it('calls every workspace, restore, and Random Note API with exact wire requests and DTOs', async () => {
    const workspaceSummaryWire = {
      id: 'named_knowledge_workspace:desk', name: 'Desk', revision: 1, updated_at: timestamp,
    }
    const restoreWire = {
      workspace_id: 'named_knowledge_workspace:desk',
      revision: 1,
      active_pane_id: 'pane-one',
      next_id: 2,
      panes: {
        'pane-one': {
          id: 'pane-one', active_tab_id: 'tab-one',
          tabs: [{
            ...snapshotWire.panes['pane-one'].tabs[0],
            target_state: 'available', target_document: descriptorWire,
          }],
        },
      },
      layout: snapshotWire.layout,
      navigation: navigationWire,
      summary: { available: 1, stale: 0, unavailable: 0, missing: 0 },
    }
    const snapshot = {
      version: 1 as const,
      activePaneId: 'pane-one', nextId: 2,
      panes: {
        'pane-one': {
          id: 'pane-one', activeTabId: 'tab-one',
          tabs: [{
            id: 'tab-one',
            target: { kind: 'document' as const, documentId: 'knowledge_engine_document:one' },
            displayLabel: 'One', viewMode: 'graph' as const,
          }],
        },
      },
      layout: { type: 'pane' as const, paneId: 'pane-one' },
      navigation: {
        utilityMode: 'bookmarks' as const, sidebarVisible: true, sidebarWidth: 360,
        activeBookmarkFolderId: 'knowledge_bookmark_folder:research', bookmarkTags: ['Evidence'],
        sourceTreeQuery: 'source', searchQuery: 'search', activeDraftId: 'draft-one',
        selectedSpaceIds: ['knowledge_engine_space:research'],
        authorityFilters: ['external_read_only' as const], metricsVisible: false,
      },
    }
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { items: [workspaceSummaryWire] } } as never)
      .mockResolvedValueOnce({ data: workspaceWire } as never)
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: workspaceWire } as never)
      .mockResolvedValueOnce({ data: { ...workspaceWire, id: 'named_knowledge_workspace:copy', name: 'Copy', name_key: 'copy', capacity_slot: 1 } } as never)
      .mockResolvedValueOnce({ data: restoreWire } as never)
      .mockResolvedValueOnce({ data: { state: 'selected', document: descriptorWire } } as never)
    vi.mocked(apiClient.patch).mockResolvedValueOnce({ data: { ...workspaceWire, name: 'Renamed', name_key: 'renamed', revision: 2 } } as never)
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: { ...receiptWire, entity_kind: 'workspace' } } as never)

    await expect(knowledgeNavigationApi.listWorkspaces()).resolves.toEqual({
      items: [{ id: 'named_knowledge_workspace:desk', name: 'Desk', revision: 1, updatedAt: timestamp }],
    })
    await expect(knowledgeNavigationApi.createWorkspace({
      operationId: 'operation-create-workspace', name: 'Desk', snapshot,
    })).resolves.toEqual(expect.objectContaining({
      snapshot: expect.objectContaining({
        activePaneId: 'pane-one',
        navigation: expect.objectContaining({ utilityMode: 'bookmarks' }),
      }),
    }))
    await knowledgeNavigationApi.getWorkspace('named_knowledge_workspace:desk')
    await knowledgeNavigationApi.updateWorkspace('named_knowledge_workspace:desk', {
      operationId: 'operation-update-workspace', expectedRevision: 1, name: 'Renamed',
    })
    await knowledgeNavigationApi.duplicateWorkspace('named_knowledge_workspace:desk', {
      operationId: 'operation-duplicate-workspace', name: 'Copy',
    })
    await knowledgeNavigationApi.deleteWorkspace('named_knowledge_workspace:desk', {
      operationId: 'operation-delete-workspace', expectedRevision: 2,
    })
    await expect(knowledgeNavigationApi.restorePlan('named_knowledge_workspace:desk', 1))
      .resolves.toEqual(expect.objectContaining({
        workspaceId: 'named_knowledge_workspace:desk',
        panes: { 'pane-one': expect.objectContaining({ activeTabId: 'tab-one' }) },
        summary: { available: 1, stale: 0, unavailable: 0, missing: 0 },
      }))
    await expect(knowledgeNavigationApi.randomNote({
      spaceIds: ['knowledge_engine_space:research'],
      authorityKinds: ['external_read_only'], tags: ['Evidence'],
    })).resolves.toEqual({
      state: 'selected', document: expect.objectContaining({ relativeLocator: 'Research/One.md' }),
    })

    expect(apiClient.get).toHaveBeenNthCalledWith(1, '/deeper-notebook/knowledge/workspaces')
    expect(apiClient.get).toHaveBeenNthCalledWith(2, '/deeper-notebook/knowledge/workspaces/named_knowledge_workspace%3Adesk')
    expect(apiClient.post).toHaveBeenNthCalledWith(1, '/deeper-notebook/knowledge/workspaces', {
      operation_id: 'operation-create-workspace', name: 'Desk', snapshot: snapshotWire,
    })
    expect(apiClient.patch).toHaveBeenCalledWith(
      '/deeper-notebook/knowledge/workspaces/named_knowledge_workspace%3Adesk',
      { operation_id: 'operation-update-workspace', expected_revision: 1, name: 'Renamed' },
    )
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      '/deeper-notebook/knowledge/workspaces/named_knowledge_workspace%3Adesk/duplicate',
      { operation_id: 'operation-duplicate-workspace', name: 'Copy' },
    )
    expect(apiClient.delete).toHaveBeenCalledWith(
      '/deeper-notebook/knowledge/workspaces/named_knowledge_workspace%3Adesk',
      { data: { operation_id: 'operation-delete-workspace', expected_revision: 2 } },
    )
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      '/deeper-notebook/knowledge/workspaces/named_knowledge_workspace%3Adesk/restore-plan',
      { revision: 1 },
    )
    expect(apiClient.post).toHaveBeenNthCalledWith(4, '/deeper-notebook/knowledge/random-note', {
      space_ids: ['knowledge_engine_space:research'],
      authority_kinds: ['external_read_only'], tags: ['Evidence'],
    })
  })

  it('rejects folder recursion over 16 levels and more than 256 total nodes before recursive parsing', async () => {
    let deep: FolderFixture = { ...folderWire }
    for (let index = 2; index <= 17; index += 1) {
      deep = {
        ...folderWire,
        id: `knowledge_bookmark_folder:level${index}`,
        children: [deep],
      }
    }
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: { items: [deep] } } as never)
    await expect(knowledgeNavigationApi.listFolders()).rejects.toThrow(/bounds/)

    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { items: Array.from({ length: 257 }, (_, index) => ({
        ...folderWire, id: `knowledge_bookmark_folder:item${index}`,
      })) },
    } as never)
    await expect(knowledgeNavigationApi.listFolders()).rejects.toThrow(/bounds/)
  })

  it.each([
    ['pane-key mismatch', (value: typeof workspaceWire) => ({
      ...value,
      snapshot: { ...value.snapshot, panes: { wrong: value.snapshot.panes['pane-one'] } },
    })],
    ['missing active tab', (value: typeof workspaceWire) => ({
      ...value,
      snapshot: {
        ...value.snapshot,
        panes: { 'pane-one': { ...value.snapshot.panes['pane-one'], active_tab_id: 'tab-missing' } },
      },
    })],
    ['reserved allocator ID', (value: typeof workspaceWire) => ({
      ...value, id: 'named_knowledge_workspace:capacity_allocator',
    })],
  ])('rejects invalid named workspace %s invariants', async (_label, corrupt) => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: corrupt(workspaceWire) } as never)
    await expect(knowledgeNavigationApi.getWorkspace('named_knowledge_workspace:desk')).rejects.toThrow()
  })

  it('rejects named workspace pane and aggregate tab totals before nested parsing', async () => {
    const panes = Object.fromEntries(Array.from({ length: 33 }, (_, index) => {
      const id = `pane-${index + 1}`
      return [id, { id, active_tab_id: null, tabs: [] }]
    }))
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: {
      ...workspaceWire,
      snapshot: { ...snapshotWire, active_pane_id: 'pane-1', panes },
    } } as never)
    await expect(knowledgeNavigationApi.getWorkspace('named_knowledge_workspace:desk'))
      .rejects.toThrow(/32 panes/)

    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: {
      ...workspaceWire,
      snapshot: {
        ...snapshotWire,
        panes: {
          'pane-one': {
            ...snapshotWire.panes['pane-one'],
            active_tab_id: null,
            tabs: Array.from({ length: 129 }, (_, index) => ({
              ...snapshotWire.panes['pane-one'].tabs[0], id: `tab-${index + 1}`,
            })),
          },
        },
      },
    } } as never)
    await expect(knowledgeNavigationApi.getWorkspace('named_knowledge_workspace:desk'))
      .rejects.toThrow(/128 tabs/)
  })

  it('rejects missing active panes and duplicate tab IDs', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: {
      ...workspaceWire,
      snapshot: { ...snapshotWire, active_pane_id: 'pane-missing' },
    } } as never)
    await expect(knowledgeNavigationApi.getWorkspace('named_knowledge_workspace:desk'))
      .rejects.toThrow(/active pane/)

    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: {
      ...workspaceWire,
      snapshot: {
        ...snapshotWire,
        panes: {
          'pane-one': {
            ...snapshotWire.panes['pane-one'],
            tabs: [
              snapshotWire.panes['pane-one'].tabs[0],
              snapshotWire.panes['pane-one'].tabs[0],
            ],
          },
        },
      },
    } } as never)
    await expect(knowledgeNavigationApi.getWorkspace('named_knowledge_workspace:desk'))
      .rejects.toThrow(/unique/)
  })

  it('rejects layouts over depth 64, duplicate split IDs, and incomplete pane coverage', async () => {
    let deepLayout: object = { type: 'pane', pane_id: 'pane-one' }
    for (let depth = 1; depth <= 64; depth += 1) {
      deepLayout = {
        type: 'split', id: `split-${depth}`, direction: 'horizontal', first_size: 50,
        first: deepLayout, second: { type: 'pane', pane_id: 'pane-one' },
      }
    }
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: {
      ...workspaceWire, snapshot: { ...snapshotWire, layout: deepLayout },
    } } as never)
    await expect(knowledgeNavigationApi.getWorkspace('named_knowledge_workspace:desk'))
      .rejects.toThrow(/depth 64/)

    const threePanes = {
      'pane-one': snapshotWire.panes['pane-one'],
      'pane-two': { id: 'pane-two', active_tab_id: null, tabs: [] },
      'pane-three': { id: 'pane-three', active_tab_id: null, tabs: [] },
    }
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: {
      ...workspaceWire,
      snapshot: {
        ...snapshotWire,
        panes: threePanes,
        layout: {
          type: 'split', id: 'split-duplicate', direction: 'horizontal', first_size: 50,
          first: { type: 'pane', pane_id: 'pane-one' },
          second: {
            type: 'split', id: 'split-duplicate', direction: 'vertical', first_size: 50,
            first: { type: 'pane', pane_id: 'pane-two' },
            second: { type: 'pane', pane_id: 'pane-three' },
          },
        },
      },
    } } as never)
    await expect(knowledgeNavigationApi.getWorkspace('named_knowledge_workspace:desk'))
      .rejects.toThrow(/split IDs/)

    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: {
      ...workspaceWire,
      snapshot: {
        ...snapshotWire,
        panes: {
          ...snapshotWire.panes,
          'pane-two': { id: 'pane-two', active_tab_id: null, tabs: [] },
        },
      },
    } } as never)
    await expect(knowledgeNavigationApi.getWorkspace('named_knowledge_workspace:desk'))
      .rejects.toThrow(/every pane/)
  })

  it('rejects unknown fields and the allocator sentinel inside stable workspace targets', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: {
      ...workspaceWire,
      snapshot: {
        ...snapshotWire,
        panes: {
          'pane-one': {
            ...snapshotWire.panes['pane-one'],
            tabs: [{
              ...snapshotWire.panes['pane-one'].tabs[0],
              target: {
                kind: 'document', document_id: 'knowledge_engine_document:one',
                root_path: 'private/path',
              },
            }],
          },
        },
      },
    } } as never)
    await expect(knowledgeNavigationApi.getWorkspace('named_knowledge_workspace:desk'))
      .rejects.toThrow()

    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: {
      ...workspaceWire,
      snapshot: {
        ...snapshotWire,
        panes: {
          'pane-one': {
            ...snapshotWire.panes['pane-one'],
            tabs: [{
              ...snapshotWire.panes['pane-one'].tabs[0],
              target: {
                kind: 'workspace',
                workspace_id: 'named_knowledge_workspace:capacity_allocator',
              },
            }],
          },
        },
      },
    } } as never)
    await expect(knowledgeNavigationApi.getWorkspace('named_knowledge_workspace:desk'))
      .rejects.toThrow(/reserved/)
  })

  it('rejects restore plans whose summaries do not match hydrated states', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: {
      workspace_id: 'named_knowledge_workspace:desk', revision: 1,
      active_pane_id: 'pane-one', next_id: 2,
      panes: {
        'pane-one': {
          id: 'pane-one', active_tab_id: 'tab-one',
          tabs: [{
            ...snapshotWire.panes['pane-one'].tabs[0],
            target_state: 'missing', target_document: null,
          }],
        },
      },
      layout: snapshotWire.layout, navigation: navigationWire,
      summary: { available: 1, stale: 0, unavailable: 0, missing: 0 },
    } } as never)

    await expect(knowledgeNavigationApi.restorePlan('named_knowledge_workspace:desk', 1))
      .rejects.toThrow(/summary/)
  })

  it('rejects unknown fields on every command family and response family', async () => {
    await expect(knowledgeNavigationApi.createBookmark({ ...bookmarkCreate, extra: true } as never))
      .rejects.toThrow()
    await expect(knowledgeNavigationApi.createFolder({
      operationId: 'operation-create-folder', name: 'Research', parentFolderId: null,
      position: 0, extra: true,
    } as never)).rejects.toThrow()
    await expect(knowledgeNavigationApi.randomNote({ tags: [], extra: true } as never))
      .rejects.toThrow()

    vi.mocked(apiClient.get).mockResolvedValue({ data: { items: [], unexpected: true } } as never)
    await expect(knowledgeNavigationApi.listWorkspaces()).rejects.toThrow()
  })
})

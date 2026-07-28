import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./client', () => ({
  default: { get: vi.fn(), put: vi.fn() },
}))

import apiClient from './client'
import {
  knowledgeWorkspaceApi,
  knowledgeWorkspaceWireSchema,
} from './knowledge-workspace'

const wireDocument = {
  version: 1,
  active_pane_id: 'pane-1',
  next_id: 2,
  panes: {
    'pane-1': {
      id: 'pane-1',
      active_tab_id: 'tab-1',
      tabs: [{
        id: 'tab-1',
        vault_id: 'vault:one',
        note_id: 'note:plan',
        title: 'Plan',
        relative_path: 'Projects/Plan.md',
        view_mode: 'reading',
      }],
    },
  },
  layout: { type: 'pane', pane_id: 'pane-1' },
} as const

describe('knowledge workspace API boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    '/Users/owner/secret.md',
    '\\Users\\owner\\secret.md',
    'C:\\Users\\owner\\secret.md',
    'C:/Users/owner/secret.md',
    '\\\\server\\share\\secret.md',
    '//server/share/secret.md',
  ])('recursively rejects absolute paths before exposing a document: %s', async (relative_path) => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        ...wireDocument,
        panes: {
          'pane-1': {
            ...wireDocument.panes['pane-1'],
            tabs: [{ ...wireDocument.panes['pane-1'].tabs[0], relative_path }],
          },
        },
      },
    } as never)

    await expect(knowledgeWorkspaceApi.get()).rejects.toThrow(/absolute path/i)
  })

  it.each([
    '/Users/owner/secret.md',
    '\\Users\\owner\\secret.md',
    'C:\\Users\\owner\\secret.md',
    'C:relative-drive-path.md',
    '\\\\server\\share\\secret.md',
    '//server/share/secret.md',
  ])('rejects absolute or drive-prefixed relative_path values in the Zod contract: %s', (relative_path) => {
    const unsafe = {
      ...wireDocument,
      panes: {
        'pane-1': {
          ...wireDocument.panes['pane-1'],
          tabs: [{ ...wireDocument.panes['pane-1'].tabs[0], relative_path }],
        },
      },
    }

    expect(() => knowledgeWorkspaceWireSchema.parse(unsafe)).toThrow(/relative to its vault/i)
  })

  it('rejects relative paths that escape their vault', () => {
    const escaping = {
      ...wireDocument,
      panes: {
        'pane-1': {
          ...wireDocument.panes['pane-1'],
          tabs: [{
            ...wireDocument.panes['pane-1'].tabs[0],
            relative_path: 'Projects/../secret.md',
          }],
        },
      },
    }

    expect(() => knowledgeWorkspaceWireSchema.parse(escaping)).toThrow(/escape/i)
  })

  it('rejects inconsistent layout references', () => {
    expect(() => knowledgeWorkspaceWireSchema.parse({
      ...wireDocument,
      layout: { type: 'pane', pane_id: 'pane-missing' },
    })).toThrow(/every pane exactly once/i)
  })

  it('rejects a hostile deeply nested layout before recursive Zod parsing', async () => {
    let layout: unknown = { type: 'pane', pane_id: 'pane-1' }
    for (let depth = 0; depth < 5_000; depth += 1) {
      layout = {
        type: 'split',
        id: `split-${depth}`,
        direction: 'horizontal',
        first: layout,
        second: { type: 'pane', pane_id: 'pane-1' },
      }
    }
    const hostile = { ...wireDocument, layout }

    expect(() => knowledgeWorkspaceWireSchema.parse(hostile))
      .toThrow(/depth 64/i)

    vi.mocked(apiClient.get).mockResolvedValue({ data: hostile } as never)
    await expect(knowledgeWorkspaceApi.get()).rejects.toThrow(/depth 64/i)
  })

  it('converts snake_case responses to the camelCase store document', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: wireDocument } as never)

    await expect(knowledgeWorkspaceApi.get()).resolves.toEqual({
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
            title: 'Plan',
            relativePath: 'Projects/Plan.md',
            viewMode: 'reading',
          }],
        },
      },
      layout: { type: 'pane', paneId: 'pane-1' },
    })
    expect(apiClient.get).toHaveBeenCalledWith('/deeper-notebook/workspace/knowledge')
  })

  it('serializes only approved snake_case fields for PUT', async () => {
    vi.mocked(apiClient.put).mockResolvedValue({ data: wireDocument } as never)
    const documentWithExtras = {
      version: 1 as const,
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
            title: 'Plan',
            relativePath: 'Projects/Plan.md',
            viewMode: 'reading' as const,
            ignoredTabField: 'not-on-the-wire',
          }],
          ignoredPaneField: true,
        },
      },
      layout: { type: 'pane' as const, paneId: 'pane-1', ignoredLayoutField: true },
      hydrated: true,
      replaceWorkspace: vi.fn(),
    }

    await knowledgeWorkspaceApi.put(documentWithExtras)

    expect(apiClient.put).toHaveBeenCalledWith(
      '/deeper-notebook/workspace/knowledge',
      wireDocument,
    )
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./client', () => ({
  default: { get: vi.fn(), put: vi.fn() },
}))

import apiClient from './client'
import {
  defaultKnowledgeWorkspace,
  knowledgeWorkspaceApi,
  knowledgeWorkspaceWireSchema,
  openKnowledgeTabSchema,
  parseKnowledgeWorkspace,
  serializeKnowledgeWorkspace,
  type KnowledgeLayoutNode,
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

const noncanonicalRelativePaths = [
  '',
  '/Users/owner/private/two.md',
  '../outside.md',
  'pages\\two.md',
  'pages//two.md',
  'pages/./two.md',
  'pages/\0two.md',
  'C:/private/two.md',
  ' pages/two.md',
  'pages/two.md ',
]

describe('knowledge workspace API boundary', () => {
  beforeEach(() => {
    vi.resetAllMocks()
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

    expect(() => knowledgeWorkspaceWireSchema.parse(unsafe))
      .toThrow(/canonical vault-relative path/i)
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

    expect(() => knowledgeWorkspaceWireSchema.parse(escaping))
      .toThrow(/canonical vault-relative path/i)
  })

  it.each(noncanonicalRelativePaths)(
    'rejects noncanonical shared path %j for wire and open-tab input',
    (relativePath) => {
      const unsafeWire = {
        ...wireDocument,
        panes: {
          'pane-1': {
            ...wireDocument.panes['pane-1'],
            tabs: [{
              ...wireDocument.panes['pane-1'].tabs[0],
              relative_path: relativePath,
            }],
          },
        },
      }

      expect(knowledgeWorkspaceWireSchema.safeParse(unsafeWire).success).toBe(false)
      expect(openKnowledgeTabSchema.safeParse({
        vaultId: 'vault:one',
        noteId: 'note:two',
        title: 'Two',
        relativePath,
      }).success).toBe(false)
    },
  )

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

  it('rejects a deeply nested camelCase layout before outbound recursive conversion', () => {
    let layout: unknown = { type: 'pane', paneId: 'pane-1' }
    for (let depth = 0; depth < 5_000; depth += 1) {
      layout = {
        type: 'split',
        id: `split-${depth}`,
        direction: 'horizontal',
        first: layout,
        second: { type: 'pane', paneId: 'pane-1' },
      }
    }
    let guardedNode = layout as Record<string, unknown>
    for (let depth = 1; depth <= 64; depth += 1) {
      guardedNode = guardedNode.first as Record<string, unknown>
    }
    Object.defineProperty(guardedNode, 'type', {
      configurable: true,
      get: () => {
        throw new Error('recursive conversion reached unsafe depth')
      },
    })

    expect(() => serializeKnowledgeWorkspace({
      ...defaultKnowledgeWorkspace(),
      layout: layout as KnowledgeLayoutNode,
    })).toThrow(/depth 64/i)
  })

  it('rejects oversized wire collections before nested tab validation', async () => {
    const tabs = Array.from({ length: 129 }, (_, index) => ({
      ...wireDocument.panes['pane-1'].tabs[0],
      id: `tab-${index + 1}`,
      note_id: `note-${index + 1}`,
      relative_path: `Notes/${index + 1}.md`,
    }))
    tabs[128] = {
      ...tabs[128],
      relative_path: '/must-not-be-deeply-validated.md',
    }

    const result = knowledgeWorkspaceWireSchema.safeParse({
      ...wireDocument,
      panes: {
        'pane-1': {
          ...wireDocument.panes['pane-1'],
          tabs,
        },
      },
    })
    expect(result.success).toBe(false)
    if (result.success) return
    const messages = result.error.issues.map((issue) => issue.message)
    expect(messages).toContain('workspace cannot contain more than 128 tabs')
    expect(messages).not.toContain('value must be a canonical vault-relative path')

    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        ...wireDocument,
        panes: {
          'pane-1': {
            ...wireDocument.panes['pane-1'],
            tabs,
          },
        },
      },
    } as never)
    await expect(knowledgeWorkspaceApi.get()).rejects
      .toThrow(/more than 128 tabs/i)
  })

  it('rejects oversized store collections before outbound tab conversion', () => {
    const document = defaultKnowledgeWorkspace()
    document.panes['pane-1'].tabs = Array.from(
      { length: 129 },
      (_, index) => ({
        id: `tab-${index + 1}`,
        vaultId: 'vault:one',
        noteId: `note-${index + 1}`,
        title: `Note ${index + 1}`,
        relativePath: `Notes/${index + 1}.md`,
        viewMode: 'reading' as const,
        sourceAuthority: 'external-vault' as const,
      }),
    )
    document.panes['pane-1'].tabs[128].relativePath =
      '/must-not-be-converted.md'
    document.panes['pane-1'].activeTabId = 'tab-1'

    expect(() => serializeKnowledgeWorkspace(document))
      .toThrow(/more than 128 tabs/i)
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
            sourceAuthority: 'external-vault',
          }],
        },
      },
      layout: { type: 'pane', paneId: 'pane-1' },
    })
    expect(apiClient.get).toHaveBeenCalledWith('/deeper-notebook/workspace/knowledge')
  })

  it('loads legacy version-1 tabs as external-vault authority', () => {
    const parsed = parseKnowledgeWorkspace(wireDocument)

    expect(parsed.panes['pane-1'].tabs[0].sourceAuthority)
      .toBe('external-vault')
  })

  it('always serializes explicit source authority for legacy workspace tabs', () => {
    expect(serializeKnowledgeWorkspace(defaultKnowledgeWorkspace())).toMatchObject({
      panes: { 'pane-1': { tabs: [] } },
    })
    const parsed = parseKnowledgeWorkspace(wireDocument)
    expect(serializeKnowledgeWorkspace(parsed).panes['pane-1'].tabs[0])
      .toMatchObject({ source_authority: 'external-vault' })
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
            sourceAuthority: 'external-vault' as const,
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
      {
        ...wireDocument,
        panes: {
          'pane-1': {
            ...wireDocument.panes['pane-1'],
            tabs: [{
              ...wireDocument.panes['pane-1'].tabs[0],
              source_authority: 'external-vault',
            }],
          },
        },
      },
    )
  })
})

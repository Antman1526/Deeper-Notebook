import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  registerKnowledgeCommandContext,
  resetKnowledgeCommandContextStore,
} from '@/lib/commands/knowledge-command-context-store'
import {
  requestCommandSurface,
  resetCommandSurfaceStore,
} from '@/lib/commands/command-surface-store'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'

const router = vi.hoisted(() => ({ push: vi.fn() }))
const dialogs = vi.hoisted(() => ({
  openSourceDialog: vi.fn(),
  openNotebookDialog: vi.fn(),
  openPodcastDialog: vi.fn(),
}))
const theme = vi.hoisted(() => ({ setTheme: vi.fn() }))
const indexed = vi.hoisted(() => ({
  runSemanticSearch: vi.fn(),
  text: { data: { results: [], total_count: 0, search_type: 'text' }, isCurrent: true },
  semantic: { data: undefined, variables: undefined, isError: false, error: null },
}))

vi.mock('next/navigation', () => ({ useRouter: () => router }))
vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: () => dialogs,
}))
vi.mock('@/lib/hooks/use-notebooks', () => ({
  useNotebooks: () => ({ data: [{ id: 'notebook-1', name: 'Research Core', description: '' }], isLoading: false }),
}))
vi.mock('@/lib/stores/theme-store', () => ({ useTheme: () => theme }))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { query?: string }) => ({
      'common.quickActions': 'Quick actions',
      'common.quickActionsDesc': 'Quick actions description',
      'common.search': 'Search',
      'common.noResults': 'No results found.',
      'common.newSource': 'New source',
      'common.newNotebook': 'New notebook',
      'common.newPodcast': 'New podcast',
      'common.light': 'Light',
      'common.dark': 'Dark',
      'common.system': 'System',
      'navigation.sources': 'Sources',
      'navigation.notebooks': 'Notebooks',
      'navigation.askAndSearch': 'Search and Ask',
      'navigation.podcasts': 'Podcasts',
      'navigation.models': 'Models',
      'navigation.transformations': 'Transformations',
      'navigation.settings': 'Settings',
      'navigation.advanced': 'Advanced',
      'navigation.nav': 'Navigation',
      'navigation.create': 'Create',
      'navigation.theme': 'Theme',
      'notebooks.title': 'Notebooks',
      'searchPage.enterSearchPlaceholder': 'Search commands',
      'searchPage.searchAndAsk': 'Search and Ask',
      'searchPage.orSearchKb': 'Or search',
      'searchPage.searchResultsFor': `Search results for ${options?.query ?? '{query}'}`,
      'searchPage.askAbout': `Ask about ${options?.query ?? '{query}'}`,
      'knowledge.commands.viewSource': 'Source',
      'knowledge.commands.splitRight': 'Split pane right',
      'knowledge.commands.requiresActiveTab': 'Requires active tab',
      'knowledge.commands.requiresActivePane': 'Requires active pane',
      'knowledge.commands.requiresMultiplePanes': 'Requires multiple panes',
      'knowledge.commands.requiresSelectedVault': 'Requires selected vault',
      'knowledge.commands.requiresFileTree': 'Requires file tree',
      'knowledge.commands.requiresLinks': 'Requires links',
      'knowledge.commandUnavailable': 'Command unavailable',
      'knowledge.commands': 'Knowledge',
      'knowledge.semanticSearchFor': `Semantic search for ${options?.query ?? ''}`,
      'knowledge.semanticSearchResults': 'Semantic results',
      'knowledge.semanticUnavailable': 'Semantic search unavailable',
    }[key] ?? key),
  }),
}))
vi.mock('@/lib/hooks/use-knowledge-command-data', () => ({
  useKnowledgeCatalog: () => ({
    candidates: [],
    isLoading: false,
    failedVaultCount: 0,
    retryFailedVaults: vi.fn(),
  }),
  useKnowledgeIndexedSearch: () => indexed,
}))
vi.mock('@/lib/hooks/use-vault', () => ({
  useVaults: () => ({ data: [], isLoading: false, isError: false }),
}))

import { CommandPalette } from './CommandPalette'

function renderPalette() {
  return render(<CommandPalette />)
}

function registerKnowledgeContext() {
  const activePane = document.createElement('section')
  const fileTree = document.createElement('aside')
  const links = document.createElement('aside')
  document.body.append(activePane, fileTree, links)
  registerKnowledgeCommandContext({
    selectedVaultId: 'vault:one',
    activePaneElement: activePane,
    fileTreeElement: fileTree,
    linksElement: links,
    scanSelectedVault: vi.fn(async () => undefined),
  })
  return { activePane, fileTree, links }
}

describe('CommandPalette', () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollIntoView = vi.fn()
    router.push.mockReset()
    Object.values(dialogs).forEach(mock => mock.mockReset())
    theme.setTheme.mockReset()
    indexed.runSemanticSearch.mockReset()
    indexed.text = { data: { results: [], total_count: 0, search_type: 'text' }, isCurrent: true }
    indexed.semantic = { data: undefined, variables: undefined, isError: false, error: null }
    resetCommandSurfaceStore()
    resetKnowledgeCommandContextStore()
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
  })

  it('preserves global palette commands and closes on a second Cmd+K', async () => {
    renderPalette()
    fireEvent.keyDown(document, { key: 'k', metaKey: true })

    expect(await screen.findByRole('dialog', { name: 'Quick actions' })).toBeVisible()
    expect(screen.getByRole('option', { name: 'Sources' })).toBeVisible()
    expect(screen.getByRole('option', { name: 'New notebook' })).toBeVisible()
    expect(screen.getByRole('option', { name: 'Dark' })).toBeVisible()
    expect(screen.getByRole('option', { name: 'Research Core' })).toBeVisible()

    fireEvent.keyDown(document, { key: 'k', metaKey: true })
    expect(screen.queryByRole('dialog', { name: 'Quick actions' })).toBeNull()
  })

  it('preserves Cmd+N, Cmd+U, and Cmd+/ global shortcuts', () => {
    renderPalette()
    fireEvent.keyDown(document, { key: 'n', metaKey: true })
    fireEvent.keyDown(document, { key: 'u', metaKey: true })
    fireEvent.keyDown(document, { key: '/', metaKey: true })

    expect(dialogs.openNotebookDialog).toHaveBeenCalledTimes(1)
    expect(dialogs.openSourceDialog).toHaveBeenCalledTimes(1)
    expect(router.push).toHaveBeenCalledWith('/search')
  })

  it('shows only safe Knowledge commands for a slash invocation', async () => {
    const elements = registerKnowledgeContext()
    useKnowledgeWorkspaceStore.getState().openTab({
      vaultId: 'vault:one', noteId: 'note:one', title: 'One', relativePath: 'One.md',
    })
    renderPalette()
    act(() => requestCommandSurface('slash', '/'))

    expect(await screen.findByRole('option', { name: 'Source' })).toBeVisible()
    expect(screen.getByRole('option', { name: 'Split pane right' })).toBeVisible()
    expect(screen.queryByRole('option', { name: 'Sources' })).toBeNull()
    expect(screen.queryByRole('option', { name: 'New notebook' })).toBeNull()
    expect(screen.queryByRole('option', { name: 'Dark' })).toBeNull()
    elements.activePane.remove()
    elements.fileTree.remove()
    elements.links.remove()
  })

  it('executes a safe command in the active pane without closing for unavailable context', async () => {
    const elements = registerKnowledgeContext()
    useKnowledgeWorkspaceStore.getState().openTab({
      vaultId: 'vault:one', noteId: 'note:one', title: 'One', relativePath: 'One.md',
    })
    renderPalette()
    act(() => requestCommandSurface('slash', '/'))
    fireEvent.click(await screen.findByRole('option', { name: 'Source' }))
    await waitFor(() => {
      const workspace = useKnowledgeWorkspaceStore.getState()
      const pane = workspace.panes[workspace.activePaneId]
      expect(pane.tabs.find(tab => tab.id === pane.activeTabId)?.viewMode).toBe('source')
    })
    elements.activePane.remove()
    elements.fileTree.remove()
    elements.links.remove()
  })

  it('offers semantic search only after explicit selection', async () => {
    registerKnowledgeContext()
    renderPalette()
    fireEvent.keyDown(document, { key: 'k', metaKey: true })
    fireEvent.change(await screen.findByRole('combobox'), {
      target: { value: 'research' },
    })

    fireEvent.click(screen.getByRole('option', { name: 'Semantic search for research' }))
    expect(indexed.runSemanticSearch).toHaveBeenCalledTimes(1)
  })
})

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  registerKnowledgeCommandContext,
  resetKnowledgeCommandContextStore,
} from '@/lib/commands/knowledge-command-context-store'
import {
  requestCommandSurface,
  resetCommandSurfaceStore,
  useCommandSurfaceStore,
} from '@/lib/commands/command-surface-store'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import { useThemeStore } from '@/lib/stores/theme-store'
import type { SearchResponse } from '@/lib/types/search'

const router = vi.hoisted(() => ({ push: vi.fn() }))
const deeperNotebookFetch = vi.hoisted(() => ({ deeperNotebookFetch: vi.fn() }))
const dialogs = vi.hoisted(() => ({
  openSourceDialog: vi.fn(),
  openNotebookDialog: vi.fn(),
  openPodcastDialog: vi.fn(),
}))
const indexed = vi.hoisted(() => ({
  runSemanticSearch: vi.fn(),
  text: {
    data: { results: [], total_count: 0, search_type: 'text' } as SearchResponse | undefined,
    isCurrent: true,
  },
  semantic: {
    data: undefined as SearchResponse | undefined,
    variables: undefined as string | undefined,
    isError: false,
    error: null as Error | null,
  },
}))
const commandData = vi.hoisted(() => ({
  catalog: {
    candidates: [] as Array<{
      key: string
      vaultId: string
      noteId: string
      vaultName: string
      format: 'markdown'
      title: string
      relativePath: string
      isOpen: boolean
    }>,
    isLoading: false,
    failedVaultCount: 0,
    retryFailedVaults: vi.fn(),
  },
}))

vi.mock('next/navigation', () => ({ useRouter: () => router }))
vi.mock('@/lib/api/deeper-notebook', () => deeperNotebookFetch)
vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: () => dialogs,
}))
vi.mock('@/lib/hooks/use-notebooks', () => ({
  useNotebooks: () => ({ data: [{ id: 'notebook-1', name: 'Research Core', description: '' }], isLoading: false }),
}))
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
      'knowledge.commands.closePane': 'Close pane',
      'knowledge.commands.scanVault': 'Scan vault',
      'knowledge.commands.focusFiles': 'Focus vault files',
      'knowledge.commands.focusPane': 'Focus active pane',
      'knowledge.commands.focusLinks': 'Focus note links',
      'knowledge.commands.bookmarkCurrent': 'Bookmark current target',
      'knowledge.commands.openBookmarks': 'Open bookmarks',
      'knowledge.commands.randomNote': 'Random Note',
      'knowledge.commands.openWorkspaces': 'Open workspaces',
      'knowledge.commands.saveWorkspaceAs': 'Save workspace as',
      'knowledge.commands.replaceWorkspace': 'Replace workspace',
      'knowledge.commands.toggleMetrics': 'Toggle document metrics',
      'knowledge.overlay.today': 'Today',
      'knowledge.overlay.newUnique': 'New unique note',
      'knowledge.commands.splitRight': 'Split pane right',
      'knowledge.commands.requiresActiveTab': 'Requires active tab',
      'knowledge.commands.requiresActivePane': 'Requires active pane',
      'knowledge.commands.requiresMultiplePanes': 'Requires multiple panes',
      'knowledge.commands.requiresSelectedVault': 'Requires selected vault',
      'knowledge.commands.requiresFileTree': 'Requires file tree',
      'knowledge.commands.requiresLinks': 'Requires links',
      'knowledge.commandUnavailable': 'Command unavailable',
      'knowledge.knowledgeCommands': 'Knowledge commands',
      'knowledge.semanticSearchFor': `Semantic search for ${options?.query ?? ''}`,
      'knowledge.semanticSearchResults': 'Semantic results',
      'knowledge.semanticUnavailable': 'Semantic search unavailable',
    }[key] ?? key),
  }),
}))
vi.mock('@/lib/hooks/use-knowledge-command-data', () => ({
  useKnowledgeCatalog: () => commandData.catalog,
  useKnowledgeIndexedSearch: () => indexed,
}))
vi.mock('@/lib/hooks/use-vault', () => ({
  useVaults: () => ({ data: [], isLoading: false, isError: false }),
}))
vi.mock('@/lib/hooks/use-overlay', () => ({
  useOverlayNotes: () => ({ data: [], isLoading: false, isError: false }),
}))
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => children,
  DropdownMenuTrigger: ({ children }: { children: ReactNode }) => children,
  DropdownMenuContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick, ...props }: { children: ReactNode; onClick?: () => void; 'aria-current'?: 'true' }) => (
    <button onClick={onClick} {...props}>{children}</button>
  ),
  DropdownMenuLabel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
}))

import { CommandPalette } from './CommandPalette'
import { ThemeGallery } from '@/components/deeper-notebook/ThemeGallery'
import { ThemeSwitcher } from '@/components/deeper-notebook/ThemeSwitcher'
import { ThemeProvider } from '@/components/providers/ThemeProvider'

function renderPalette() {
  return render(<CommandPalette />)
}

function registerKnowledgeContext(options: {
  scanSelectedVault?: () => Promise<void>
  openTodayOverlay?: () => Promise<void>
  openUniqueOverlayDialog?: () => void
  bookmarkCurrentTarget?: () => Promise<void>
  openBookmarks?: () => void
  randomNote?: () => Promise<void>
  openWorkspaces?: () => void
  saveWorkspaceAs?: () => void
  replaceWorkspace?: () => void
  toggleMetrics?: () => void
} = {}) {
  const activePane = document.createElement('section')
  const fileTree = document.createElement('aside')
  const links = document.createElement('aside')
  document.body.append(activePane, fileTree, links)
  registerKnowledgeCommandContext({
    selectedVaultId: 'vault:one',
    activePaneElement: activePane,
    fileTreeElement: fileTree,
    linksElement: links,
    scanSelectedVault: options.scanSelectedVault ?? vi.fn(async () => undefined),
    openTodayOverlay: options.openTodayOverlay ?? vi.fn(async () => undefined),
    openUniqueOverlayDialog: options.openUniqueOverlayDialog ?? vi.fn(),
    bookmarkCurrentTarget: options.bookmarkCurrentTarget ?? vi.fn(async () => undefined),
    openBookmarks: options.openBookmarks ?? vi.fn(),
    randomNote: options.randomNote ?? vi.fn(async () => undefined),
    openWorkspaces: options.openWorkspaces ?? vi.fn(),
    saveWorkspaceAs: options.saveWorkspaceAs ?? vi.fn(),
    replaceWorkspace: options.replaceWorkspace ?? vi.fn(),
    toggleMetrics: options.toggleMetrics ?? vi.fn(),
  })
  return { activePane, fileTree, links }
}

describe('CommandPalette', () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollIntoView = vi.fn()
    router.push.mockReset()
    Object.values(dialogs).forEach(mock => mock.mockReset())
    localStorage.clear()
    document.documentElement.dataset.theme = ''
    document.documentElement.className = ''
    useThemeStore.setState({ theme: 'system', legacyThemeOverride: false, appliedTheme: 'light' })
    deeperNotebookFetch.deeperNotebookFetch.mockResolvedValue({
      json: async () => ({ theme: 'light-blue' }),
    })
    indexed.runSemanticSearch.mockReset()
    commandData.catalog.candidates = []
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

  it.each([
    ['Light', 'light'],
    ['Dark', 'dark'],
    ['System', 'system'],
  ] as const)('routes the %s palette command through the live legacy theme setter', async (label, value) => {
    renderPalette()
    fireEvent.keyDown(document, { key: 'k', metaKey: true })

    fireEvent.click(await screen.findByRole('option', { name: label }))

    await waitFor(() => expect(useThemeStore.getState().theme).toBe(value))
  })

  it('keeps picker and painted authority on a newer canonical selection after a CommandPalette choice', async () => {
    render(
      <ThemeProvider>
        <ThemeSwitcher />
        <ThemeGallery />
        <CommandPalette />
      </ThemeProvider>,
    )

    fireEvent.keyDown(document, { key: 'k', metaKey: true })
    fireEvent.click(await screen.findByRole('option', { name: 'Dark' }))
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))

    fireEvent.click(screen.getByRole('button', { name: 'Apply Archive Paper' }))

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('archive-paper'))
    expect(localStorage.getItem('dn-theme')).toBe('archive-paper')
    expect(localStorage.getItem('onp-theme')).toBe('archive-paper')
    expect(screen.getByRole('button', { name: 'Archive Paper Current theme' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('article', { name: 'Archive Paper theme' })).toHaveTextContent('Current')
    expect(document.documentElement).not.toHaveClass('dark')
    expect(useThemeStore.getState().legacyThemeOverride).toBe(false)
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

  it('does not open from editable targets but lets a second Cmd+K close the palette', async () => {
    const input = document.createElement('input')
    const editable = document.createElement('div')
    Object.defineProperty(editable, 'isContentEditable', { value: true })
    document.body.append(input, editable)
    renderPalette()

    fireEvent.keyDown(input, { key: 'k', metaKey: true })
    fireEvent.keyDown(editable, { key: 'k', metaKey: true })
    expect(screen.queryByRole('dialog', { name: 'Quick actions' })).toBeNull()

    fireEvent.keyDown(document, { key: 'k', metaKey: true })
    expect(await screen.findByRole('dialog', { name: 'Quick actions' })).toBeVisible()
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'k', metaKey: true })
    expect(screen.queryByRole('dialog', { name: 'Quick actions' })).toBeNull()
    input.remove()
    editable.remove()
  })

  it('shows only safe Knowledge commands for a slash invocation', async () => {
    const elements = registerKnowledgeContext()
    useKnowledgeWorkspaceStore.getState().openTab({
      vaultId: 'vault:one', noteId: 'note:one', title: 'One', relativePath: 'One.md',
    })
    renderPalette()
    act(() => requestCommandSurface('slash', '/'))

    expect(await screen.findByText('Knowledge commands')).toBeVisible()
    expect(await screen.findByRole('option', { name: 'Source' })).toBeVisible()
    expect(await screen.findByRole('option', { name: 'Today' })).toBeVisible()
    expect(await screen.findByRole('option', { name: 'New unique note' })).toBeVisible()
    expect(screen.getByRole('option', { name: 'Split pane right' })).toBeVisible()
    expect(screen.queryByRole('option', { name: 'Sources' })).toBeNull()
    expect(screen.queryByRole('option', { name: 'New notebook' })).toBeNull()
    expect(screen.queryByRole('option', { name: 'Dark' })).toBeNull()
    elements.activePane.remove()
    elements.fileTree.remove()
    elements.links.remove()
  })

  it('executes app-owned overlay actions from slash commands', async () => {
    const openTodayOverlay = vi.fn(async () => undefined)
    const openUniqueOverlayDialog = vi.fn()
    const elements = registerKnowledgeContext({ openTodayOverlay, openUniqueOverlayDialog })
    renderPalette()
    act(() => requestCommandSurface('slash', '/'))
    fireEvent.click(await screen.findByRole('option', { name: 'Today' }))
    await waitFor(() => expect(openTodayOverlay).toHaveBeenCalledOnce())

    act(() => requestCommandSurface('slash', '/'))
    fireEvent.click(await screen.findByRole('option', { name: 'New unique note' }))
    await waitFor(() => expect(openUniqueOverlayDialog).toHaveBeenCalledOnce())
    elements.activePane.remove()
    elements.fileTree.remove()
    elements.links.remove()
  })

  it.each([
    ['Bookmark current target', 'bookmarkCurrentTarget'],
    ['Open bookmarks', 'openBookmarks'],
    ['Random Note', 'randomNote'],
    ['Open workspaces', 'openWorkspaces'],
    ['Save workspace as', 'saveWorkspaceAs'],
    ['Replace workspace', 'replaceWorkspace'],
    ['Toggle document metrics', 'toggleMetrics'],
  ] as const)('executes %s through the registered UI callback', async (label, callback) => {
    const callbacks = {
      bookmarkCurrentTarget: vi.fn(async () => undefined),
      openBookmarks: vi.fn(),
      randomNote: vi.fn(async () => undefined),
      openWorkspaces: vi.fn(),
      saveWorkspaceAs: vi.fn(),
      replaceWorkspace: vi.fn(),
      toggleMetrics: vi.fn(),
    }
    const elements = registerKnowledgeContext(callbacks)
    useKnowledgeWorkspaceStore.getState().openTab({
      vaultId: 'vault:one', noteId: 'note:one', title: 'One', relativePath: 'One.md',
    })
    renderPalette()
    act(() => requestCommandSurface('slash', '/'))

    fireEvent.click(await screen.findByRole('option', { name: label }))
    await waitFor(() => expect(callbacks[callback]).toHaveBeenCalledOnce())
    Object.values(elements).forEach(element => element.remove())
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

  it('keeps disabled commands visible without closing the palette', async () => {
    registerKnowledgeContext()
    renderPalette()
    act(() => requestCommandSurface('slash', '/'))

    const closePane = await screen.findByRole('option', { name: /Close pane/ })
    expect(closePane).toHaveAttribute('data-disabled', 'true')
    fireEvent.click(closePane)
    expect(screen.getByRole('dialog', { name: 'Quick actions' })).toBeVisible()
  })

  it('announces a live rejection without closing', async () => {
    const elements = registerKnowledgeContext({
      scanSelectedVault: vi.fn(async () => {
        registerKnowledgeCommandContext({
          selectedVaultId: 'vault:one',
          activePaneElement: elements.activePane,
          fileTreeElement: elements.fileTree,
          linksElement: elements.links,
          scanSelectedVault: async () => undefined,
        })
      }),
    })
    renderPalette()
    act(() => requestCommandSurface('slash', '/'))

    fireEvent.click(await screen.findByRole('option', { name: 'Scan vault' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Command unavailable')
    expect(screen.getByRole('dialog', { name: 'Quick actions' })).toBeVisible()
  })

  it('re-announces a second live context rejection in the same open session', async () => {
    const elements = registerKnowledgeContext()
    const rejectLiveContext = vi.fn(async () => {
      registerKnowledgeCommandContext({
        selectedVaultId: 'vault:one',
        activePaneElement: elements.activePane,
        fileTreeElement: elements.fileTree,
        linksElement: elements.links,
        scanSelectedVault: rejectLiveContext,
      })
    })
    registerKnowledgeCommandContext({
      selectedVaultId: 'vault:one',
      activePaneElement: elements.activePane,
      fileTreeElement: elements.fileTree,
      linksElement: elements.links,
      scanSelectedVault: rejectLiveContext,
    })
    renderPalette()
    act(() => requestCommandSurface('slash', '/'))

    fireEvent.click(await screen.findByRole('option', { name: 'Scan vault' }))
    const firstStatus = await screen.findByRole('status')
    fireEvent.click(await screen.findByRole('option', { name: 'Scan vault' }))
    await waitFor(() => expect(screen.getByRole('status')).not.toBe(firstStatus))
    expect(screen.getByRole('status')).toHaveTextContent('Command unavailable')
  })

  it('restores focus to the command invoker after closing', async () => {
    const invoker = document.createElement('button')
    document.body.append(invoker)
    renderPalette()
    act(() => requestCommandSurface('global', '', invoker))
    expect(await screen.findByRole('dialog', { name: 'Quick actions' })).toBeVisible()

    fireEvent.keyDown(document, { key: 'k', metaKey: true })
    await waitFor(() => expect(invoker).toHaveFocus())
    invoker.remove()
  })

  it.each([
    ['Focus vault files', 'fileTree'],
    ['Focus active pane', 'activePane'],
    ['Focus note links', 'links'],
  ] as const)('leaves focus on the requested region for %s', async (label, target) => {
    const invoker = document.createElement('button')
    document.body.append(invoker)
    const elements = registerKnowledgeContext()
    Object.values(elements).forEach(element => { element.tabIndex = -1 })
    renderPalette()
    act(() => requestCommandSurface('slash', '/', invoker))

    fireEvent.click(await screen.findByRole('option', { name: label }))
    await waitFor(() => expect(document.activeElement).toBe(elements[target]))
    expect(screen.queryByRole('dialog', { name: 'Quick actions' })).toBeNull()
    invoker.remove()
    Object.values(elements).forEach(element => element.remove())
  })

  it.each(['global', 'slash'] as const)(
    'consumes a handled %s request so it does not replay after remount',
    async (kind) => {
      if (kind === 'slash') registerKnowledgeContext()
      const invoker = document.createElement('button')
      document.body.append(invoker)
      const first = renderPalette()
      act(() => requestCommandSurface(kind, kind === 'slash' ? '/' : '', invoker))
      const dialog = await screen.findByRole('dialog', { name: 'Quick actions' })
      fireEvent.keyDown(within(dialog).getByRole('combobox'), { key: 'Escape' })
      await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
      await waitFor(() => expect(invoker).toHaveFocus())
      expect(useCommandSurfaceStore.getState()).toMatchObject({
        kind: null,
        initialQuery: '',
        invoker: null,
      })

      first.unmount()
      renderPalette()
      expect(screen.queryByRole('dialog', { name: 'Quick actions' })).toBeNull()
      invoker.remove()
    },
  )

  it('renders exact catalog results before accepted indexed results', async () => {
    registerKnowledgeContext()
    commandData.catalog.candidates = [{
      key: 'vault:one\0note:exact', vaultId: 'vault:one', noteId: 'note:exact',
      vaultName: 'Fixture', format: 'markdown', title: 'Research exact',
      relativePath: 'Research/exact.md', isOpen: false,
    }]
    indexed.text = {
      data: { results: [{
        id: 'note:indexed', title: 'Research indexed', parent_id: 'parent', final_score: 1,
        created: '', updated: '', vault_provenance: {
          canonical_external: true, vault_id: 'vault:one', relative_path: 'Research/indexed.md', source_hash: 'a'.repeat(64),
        },
      }], total_count: 1, search_type: 'text' },
      isCurrent: true,
    }
    renderPalette()
    fireEvent.keyDown(document, { key: 'k', metaKey: true })
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'research' } })

    const exact = await screen.findByRole('option', { name: 'Research exact' })
    const indexedResult = screen.getByRole('option', { name: 'Research indexed' })
    expect(exact.compareDocumentPosition(indexedResult) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('routes no-provenance text and semantic results to Search and omits invalid provenance', async () => {
    registerKnowledgeContext()
    const invalid = {
      id: 'note:invalid', title: 'Unsafe result', parent_id: 'parent', final_score: 1,
      created: '', updated: '', vault_provenance: {
        canonical_external: true, vault_id: 'vault:one', relative_path: '/unsafe.md', source_hash: 'not-a-hash',
      },
    }
    const noProvenance = {
      id: 'result:search', title: 'Research result', parent_id: 'parent', final_score: 1,
      created: '', updated: '',
    }
    indexed.text = { data: { results: [invalid, noProvenance], total_count: 2, search_type: 'text' }, isCurrent: true }
    indexed.semantic = { data: { results: [invalid, noProvenance], total_count: 2, search_type: 'vector' }, variables: 'research', isError: false, error: null }
    renderPalette()
    fireEvent.keyDown(document, { key: 'k', metaKey: true })
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'research' } })

    expect(await screen.findAllByRole('option', { name: 'Research result' })).toHaveLength(2)
    expect(screen.queryByRole('option', { name: 'Unsafe result' })).toBeNull()
    fireEvent.click(screen.getAllByRole('option', { name: 'Research result' })[1])
    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/search?q=research&mode=search'))
  })

  it('suppresses stale semantic results and routes embedding errors to model settings', async () => {
    registerKnowledgeContext()
    indexed.semantic = {
      data: { results: [{ id: 'note:stale', title: 'Stale semantic', parent_id: 'parent', final_score: 1, created: '', updated: '' }], total_count: 1, search_type: 'vector' },
      variables: 'older query', isError: true, error: new Error('Vector search requires an embedding model'),
    }
    renderPalette()
    fireEvent.keyDown(document, { key: 'k', metaKey: true })
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'research' } })

    expect(screen.queryByRole('option', { name: 'Stale semantic' })).toBeNull()
    fireEvent.click(screen.getByRole('option', { name: 'Semantic search unavailable' }))
    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/settings/api-keys'))
  })

  it('routes an Axios-shaped embedding configuration error to model settings', async () => {
    registerKnowledgeContext()
    indexed.semantic = {
      data: undefined,
      variables: 'research',
      isError: true,
      error: {
        response: {
          status: 400,
          data: { detail: 'Vector search requires an embedding model' },
        },
      } as unknown as Error,
    }
    renderPalette()
    fireEvent.keyDown(document, { key: 'k', metaKey: true })
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'research' } })

    fireEvent.click(screen.getByRole('option', { name: 'Semantic search unavailable' }))
    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/settings/api-keys'))
  })

  it('keeps the palette open when a command rejects', async () => {
    registerKnowledgeContext({ scanSelectedVault: vi.fn(async () => { throw new Error('scan failed') }) })
    renderPalette()
    act(() => requestCommandSurface('slash', '/'))

    fireEvent.click(await screen.findByRole('option', { name: 'Scan vault' }))
    expect(screen.getByRole('dialog', { name: 'Quick actions' })).toBeVisible()
  })

  it('closes after a successful scan without announcing unavailable', async () => {
    const scanSelectedVault = vi.fn(async () => undefined)
    registerKnowledgeContext({ scanSelectedVault })
    renderPalette()
    act(() => requestCommandSurface('slash', '/'))

    fireEvent.click(await screen.findByRole('option', { name: 'Scan vault' }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Quick actions' })).toBeNull())
    expect(scanSelectedVault).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('status')).toBeNull()
  })
})

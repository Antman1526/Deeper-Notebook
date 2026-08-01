'use client'

import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Book,
  Bot,
  FileText,
  Loader2,
  MessageCircleQuestion,
  Mic,
  Monitor,
  Moon,
  Plus,
  Search,
  Settings,
  Shuffle,
  Sparkles,
  Sun,
  Wrench,
} from 'lucide-react'
import type { TFunction } from 'i18next'

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import {
  availableKnowledgeCommands,
  executeKnowledgeCommand,
  type KnowledgeCommandExecutionContext,
} from '@/lib/commands/command-registry'
import {
  candidateToOpenTab,
  overlayNotesToKnowledgeCandidates,
  rankKnowledgeCatalog,
  searchResultToOpenTab,
} from '@/lib/commands/knowledge-command-catalog'
import { useOverlayNotes } from '@/lib/hooks/use-overlay'
import {
  acknowledgeCommandSurface,
  requestCommandSurface,
  useCommandSurfaceStore,
} from '@/lib/commands/command-surface-store'
import { useKnowledgeCommandContextStore } from '@/lib/commands/knowledge-command-context-store'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import { useKnowledgeCatalog, useKnowledgeIndexedSearch } from '@/lib/hooks/use-knowledge-command-data'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useVaults } from '@/lib/hooks/use-vault'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import { useTheme } from '@/lib/stores/theme-store'

const getNavigationItems = (t: TFunction) => [
  { name: t('navigation.sources'), href: '/sources', icon: FileText, keywords: ['files', 'documents', 'upload'] },
  { name: t('navigation.notebooks'), href: '/notebooks', icon: Book, keywords: ['notes', 'research', 'projects'] },
  { name: t('navigation.askAndSearch'), href: '/search', icon: Search, keywords: ['find', 'query'] },
  { name: t('navigation.podcasts'), href: '/podcasts', icon: Mic, keywords: ['audio', 'episodes', 'generate'] },
  { name: t('navigation.models'), href: '/settings/api-keys', icon: Bot, keywords: ['ai', 'llm', 'providers', 'openai', 'anthropic'] },
  { name: t('navigation.transformations'), href: '/transformations', icon: Shuffle, keywords: ['prompts', 'templates', 'actions'] },
  { name: t('navigation.settings'), href: '/settings', icon: Settings, keywords: ['preferences', 'config', 'options'] },
  { name: t('navigation.advanced'), href: '/advanced', icon: Wrench, keywords: ['debug', 'system', 'tools'] },
]

const getCreateItems = (t: TFunction) => [
  { name: t('common.newSource'), action: 'source', icon: FileText },
  { name: t('common.newNotebook'), action: 'notebook', icon: Book },
  { name: t('common.newPodcast'), action: 'podcast', icon: Mic },
]

const getThemeItems = (t: TFunction) => [
  { name: t('common.light'), value: 'light' as const, icon: Sun, keywords: ['bright', 'day'] },
  { name: t('common.dark'), value: 'dark' as const, icon: Moon, keywords: ['night'] },
  { name: t('common.system'), value: 'system' as const, icon: Monitor, keywords: ['auto', 'default'] },
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function embeddingConfigurationError(error: unknown): boolean {
  const messages: string[] = []
  if (error instanceof Error) messages.push(error.message)
  if (isRecord(error) && isRecord(error.response) && isRecord(error.response.data)) {
    const { detail, message } = error.response.data
    if (typeof detail === 'string') messages.push(detail)
    if (typeof message === 'string') messages.push(message)
  }
  return messages.some(message => /embedding model/iu.test(message))
}

export function CommandPalette() {
  const { t } = useTranslation()
  const router = useRouter()
  const commandInputId = useId()
  const surface = useCommandSurfaceStore()
  const {
    requestId: surfaceRequestId,
    kind: surfaceKind,
    initialQuery: surfaceInitialQuery,
    invoker: surfaceInvoker,
  } = surface
  const pageContext = useKnowledgeCommandContextStore()
  const workspace = useKnowledgeWorkspaceStore()
  const mounts = useVaults()
  const { openSourceDialog, openNotebookDialog, openPodcastDialog } = useCreateDialogs()
  const { setTheme } = useTheme()
  const { data: notebooks, isLoading: notebooksLoading } = useNotebooks(false)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [invocationMode, setInvocationMode] = useState<'global' | 'slash'>('global')
  const [invoker, setInvoker] = useState<HTMLElement | null>(null)
  const [commandUnavailableVersion, setCommandUnavailableVersion] = useState(0)
  const restoreInvokerRef = useRef(true)
  const navigationItems = useMemo(() => getNavigationItems(t), [t])
  const createItems = useMemo(() => getCreateItems(t), [t])
  const themeItems = useMemo(() => getThemeItems(t), [t])
  const openTabs = useMemo(
    () => Object.values(workspace.panes).flatMap(pane => pane.tabs),
    [workspace.panes],
  )
  const catalog = useKnowledgeCatalog(
    mounts.data || [],
    openTabs,
    open && invocationMode === 'global' && pageContext.context !== null,
  )
  const overlay = useOverlayNotes()
  const allKnowledgeCandidates = useMemo(
    () => [...catalog.candidates, ...overlayNotesToKnowledgeCandidates(overlay.data || [], openTabs)],
    [catalog.candidates, openTabs, overlay.data],
  )
  const indexed = useKnowledgeIndexedSearch(
    query,
    open && invocationMode === 'global' && pageContext.context !== null && query.trim().length >= 2,
  )

  useEffect(() => {
    if (surfaceRequestId === 0 || surfaceKind === null || surfaceKind === 'quick-switcher') return
    setInvocationMode(surfaceKind)
    setQuery(surfaceInitialQuery)
    setInvoker(surfaceInvoker)
    restoreInvokerRef.current = true
    setCommandUnavailableVersion(0)
    setOpen(true)
    acknowledgeCommandSurface(surfaceRequestId)
  }, [surfaceInitialQuery, surfaceInvoker, surfaceKind, surfaceRequestId])

  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const editable = target && (
        target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
      )
      if (editable && !(open && event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey))) {
        return
      }
      if (event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        event.stopPropagation()
        if (open) setOpen(false)
        else requestCommandSurface(
          'global',
          '',
          document.activeElement instanceof HTMLElement ? document.activeElement : null,
        )
        return
      }

      if (event.key === 'n' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        event.stopPropagation()
        openNotebookDialog()
      } else if (event.key === 'u' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        event.stopPropagation()
        openSourceDialog()
      } else if (event.key === '/' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        event.stopPropagation()
        router.push('/search')
      }
    }
    document.addEventListener('keydown', down, true)
    return () => document.removeEventListener('keydown', down, true)
  }, [open, openNotebookDialog, openSourceDialog, router])

  useEffect(() => {
    if (open) return
    setQuery('')
    if (!restoreInvokerRef.current) {
      restoreInvokerRef.current = true
      return
    }
    requestAnimationFrame(() => {
      if (invoker?.isConnected) invoker.focus()
    })
  }, [invoker, open])

  const closePalette = useCallback(() => setOpen(false), [])
  const handleSelect = useCallback((callback: () => void) => {
    closePalette()
    setTimeout(callback, 0)
  }, [closePalette])
  const handleNavigate = useCallback((href: string) => {
    handleSelect(() => router.push(href))
  }, [handleSelect, router])
  const handleSearch = useCallback(() => {
    if (!query.trim()) return
    handleNavigate(`/search?q=${encodeURIComponent(query)}&mode=search`)
  }, [handleNavigate, query])
  const handleAsk = useCallback(() => {
    if (!query.trim()) return
    handleNavigate(`/search?q=${encodeURIComponent(query)}&mode=ask`)
  }, [handleNavigate, query])
  const handleCreate = useCallback((action: string) => {
    handleSelect(() => {
      if (action === 'source') openSourceDialog()
      else if (action === 'notebook') openNotebookDialog()
      else if (action === 'podcast') openPodcastDialog()
    })
  }, [handleSelect, openNotebookDialog, openPodcastDialog, openSourceDialog])
  const handleTheme = useCallback((theme: 'light' | 'dark' | 'system') => {
    handleSelect(() => setTheme(theme))
  }, [handleSelect, setTheme])

  const buildKnowledgeContext = useCallback((): KnowledgeCommandExecutionContext | null => {
    const page = useKnowledgeCommandContextStore.getState()
    if (page.generation !== pageContext.generation || !page.context) return null
    const live = useKnowledgeWorkspaceStore.getState()
    const pane = live.panes[live.activePaneId]
    const activeTab = pane?.tabs.find(tab => tab.id === pane.activeTabId) ?? pane?.tabs[0]
    const activePaneElement = page.context.activePaneElement
    return {
      activePaneId: pane?.id ?? null,
      activeTabId: activeTab?.id ?? null,
      paneCount: Object.keys(live.panes).length,
      selectedVaultId: page.context.selectedVaultId,
      setViewMode: mode => {
        const current = useKnowledgeWorkspaceStore.getState()
        const currentPane = current.panes[current.activePaneId]
        const tabId = currentPane?.activeTabId ?? currentPane?.tabs[0]?.id
        if (currentPane && tabId) current.setTabViewMode(currentPane.id, tabId, mode)
      },
      splitPane: direction => {
        const current = useKnowledgeWorkspaceStore.getState()
        if (current.panes[current.activePaneId]) current.splitPane(current.activePaneId, direction)
      },
      closePane: () => {
        const current = useKnowledgeWorkspaceStore.getState()
        current.closePane(current.activePaneId)
      },
      closeTab: () => {
        const current = useKnowledgeWorkspaceStore.getState()
        const currentPane = current.panes[current.activePaneId]
        const tabId = currentPane?.activeTabId ?? currentPane?.tabs[0]?.id
        if (currentPane && tabId) current.closeTab(currentPane.id, tabId)
      },
      scanSelectedVault: page.context.scanSelectedVault ?? null,
      openTodayOverlay: page.context.openTodayOverlay ?? null,
      openUniqueOverlayDialog: page.context.openUniqueOverlayDialog ?? null,
      focusFileTree: page.context.fileTreeElement?.isConnected
        ? () => page.context?.fileTreeElement?.focus()
        : null,
      focusActivePane: activePaneElement?.isConnected
        ? () => activePaneElement.focus()
        : null,
      focusLinks: page.context.linksElement?.isConnected
        ? () => page.context?.linksElement?.focus()
        : null,
      bookmarkCurrentTarget: page.context.bookmarkCurrentTarget ?? null,
      openBookmarks: page.context.openBookmarks ?? null,
      randomNote: page.context.randomNote ?? null,
      openWorkspaces: page.context.openWorkspaces ?? null,
      saveWorkspaceAs: page.context.saveWorkspaceAs ?? null,
      replaceWorkspace: page.context.replaceWorkspace ?? null,
      toggleMetrics: page.context.toggleMetrics ?? null,
      researchModeAvailability: page.context.researchModeAvailability ?? {
        read: { available: false, reason: 'Research modes are unavailable' },
        write: { available: false, reason: 'Research modes are unavailable' },
        ask: { available: false, reason: 'Research modes are unavailable' },
        search: { available: false, reason: 'Research modes are unavailable' },
        graph: { available: false, reason: 'Research modes are unavailable' },
        podcast: { available: false, reason: 'Research modes are unavailable' },
      },
      openResearchMode: page.context.openResearchMode ?? null,
      moveTab: offset => {
        const current = useKnowledgeWorkspaceStore.getState()
        const currentPane = current.panes[current.activePaneId]
        const activeIndex = currentPane?.tabs.findIndex(tab => tab.id === currentPane.activeTabId) ?? -1
        if (!currentPane?.tabs.length || activeIndex < 0) return
        const target = currentPane.tabs[(activeIndex + offset + currentPane.tabs.length) % currentPane.tabs.length]
        current.activateTab(currentPane.id, target.id)
      },
    }
  }, [pageContext.generation])

  const knowledgeContext = buildKnowledgeContext()
  const knowledgeCommands = knowledgeContext
    ? availableKnowledgeCommands(knowledgeContext, invocationMode)
    : []
  const queryLower = query.toLowerCase().trim()
  const commandFilterQuery = invocationMode === 'slash'
    ? query.replace(/^\/+/, '')
    : query
  const hasCommandMatch = queryLower.length > 0 && (
    navigationItems.some(item => item.name.toLowerCase().includes(queryLower) || item.keywords.some(keyword => keyword.includes(queryLower)))
    || createItems.some(item => item.name.toLowerCase().includes(queryLower))
    || themeItems.some(item => item.name.toLowerCase().includes(queryLower) || item.keywords.some(keyword => keyword.includes(queryLower)))
    || (notebooks?.some(notebook => notebook.name.toLowerCase().includes(queryLower) || notebook.description?.toLowerCase().includes(queryLower)) ?? false)
  )
  const showSearchFirst = invocationMode === 'global' && query.trim() && !hasCommandMatch
  const exactCandidates = useMemo(
    () => invocationMode === 'global' && open && query.trim().length >= 2
      ? rankKnowledgeCatalog(allKnowledgeCandidates, query, 8)
      : [],
    [allKnowledgeCandidates, invocationMode, open, query],
  )
  const indexedResults = useMemo(() => (
    invocationMode === 'global' && open && indexed.text.isCurrent
      ? indexed.text.data?.results || []
      : []
  ), [indexed.text.data?.results, indexed.text.isCurrent, invocationMode, open])
  const semanticResults = useMemo(() => (
    invocationMode === 'global' && open && indexed.semantic.variables === query.trim()
      ? indexed.semantic.data?.results || []
      : []
  ), [indexed.semantic.data?.results, indexed.semantic.variables, invocationMode, open, query])

  const executeKnowledge = useCallback(async (id: Parameters<typeof executeKnowledgeCommand>[0]) => {
    const generation = pageContext.generation
    const liveContext = buildKnowledgeContext()
    const focusAfterClose = id === 'knowledge.focus-files'
      ? liveContext?.focusFileTree
      : id === 'knowledge.focus-pane'
        ? liveContext?.focusActivePane
        : id === 'knowledge.focus-links'
          ? liveContext?.focusLinks
          : null
    try {
      if (
        !liveContext
        || !await executeKnowledgeCommand(id, liveContext)
        || useKnowledgeCommandContextStore.getState().generation !== generation
      ) {
        setCommandUnavailableVersion(version => version + 1)
        return
      }
    } catch {
      return
    }
    if (focusAfterClose) restoreInvokerRef.current = false
    closePalette()
    if (focusAfterClose) setTimeout(focusAfterClose, 0)
  }, [buildKnowledgeContext, closePalette, pageContext.generation])

  const selectTab = useCallback((tab: ReturnType<typeof searchResultToOpenTab>) => {
    if (!tab) return
    useKnowledgeWorkspaceStore.getState().openTab(tab)
    closePalette()
  }, [closePalette])

  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      title={t('common.quickActions')}
      description={t('common.quickActionsDesc')}
      className="sm:max-w-lg"
    >
      <div className="relative">
        {invocationMode === 'slash' && (
          <span aria-hidden="true" className="pointer-events-none absolute left-10 top-3 z-10 text-sm">
            /
          </span>
        )}
        <CommandInput
          id={commandInputId}
          name="command-search"
          placeholder={t('searchPage.enterSearchPlaceholder')}
          value={commandFilterQuery}
          onValueChange={(value) => setQuery(invocationMode === 'slash' ? `/${value}` : value)}
          aria-label={t('common.search')}
          autoComplete="off"
          className={invocationMode === 'slash' ? 'pl-3' : undefined}
        />
      </div>
      {commandUnavailableVersion > 0 && (
        <p key={commandUnavailableVersion} aria-live="polite" role="status" className="sr-only">
          {t('knowledge.commandUnavailable')}
        </p>
      )}
      <CommandList>
        <CommandEmpty>{t('common.noResults', 'No results found.')}</CommandEmpty>
        {invocationMode === 'global' && showSearchFirst && (
          <CommandGroup heading={t('searchPage.searchAndAsk')} forceMount>
            <CommandItem value={`__search__ ${query}`} onSelect={handleSearch} forceMount>
              <Search className="h-4 w-4" />
              <span>{t('searchPage.searchResultsFor').replace('{query}', query)}</span>
            </CommandItem>
            <CommandItem value={`__ask__ ${query}`} onSelect={handleAsk} forceMount>
              <MessageCircleQuestion className="h-4 w-4" />
              <span>{t('searchPage.askAbout').replace('{query}', query)}</span>
            </CommandItem>
          </CommandGroup>
        )}
        {knowledgeContext && (
          <CommandGroup heading={t('knowledge.knowledgeCommands')}>
            {knowledgeCommands.map(command => (
              <CommandItem
                key={command.id}
                value={`${command.labelKey} ${command.aliases.join(' ')} ${command.keywords.join(' ')}`}
                disabled={!command.available}
                onSelect={() => void executeKnowledge(command.id)}
              >
                <span>{t(command.labelKey)}</span>
                {!command.available && (command.unavailableReason || command.unavailableReasonKey) && (
                  <span className="ml-auto text-xs text-muted-foreground">
                    {command.unavailableReason || t(command.unavailableReasonKey!)}
                  </span>
                )}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {invocationMode === 'global' && (
          <>
            <CommandGroup heading={t('navigation.nav')}>
              {navigationItems.map(item => (
                <CommandItem key={item.href} value={`${item.name} ${item.keywords.join(' ')}`} onSelect={() => handleNavigate(item.href)}>
                  <item.icon className="h-4 w-4" />
                  <span>{item.name}</span>
                </CommandItem>
              ))}
            </CommandGroup>
            {(notebooksLoading || (notebooks && notebooks.length > 0)) && (
              <CommandGroup heading={t('notebooks.title')}>
                {notebooksLoading ? (
                  <CommandItem disabled><Loader2 className="h-4 w-4 animate-spin" /><span>{t('common.loading')}</span></CommandItem>
                ) : notebooks!.map(notebook => (
                  <CommandItem key={notebook.id} value={`notebook ${notebook.name} ${notebook.description || ''}`} onSelect={() => handleNavigate(`/notebooks/${notebook.id}`)}>
                    <Book className="h-4 w-4" /><span>{notebook.name}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            <CommandGroup heading={t('navigation.create')}>
              {createItems.map(item => (
                <CommandItem key={item.action} value={`create ${item.name}`} onSelect={() => handleCreate(item.action)}>
                  <Plus className="h-4 w-4" /><span>{item.name}</span>
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandGroup heading={t('navigation.theme')}>
              {themeItems.map(item => (
                <CommandItem key={item.value} value={`theme ${item.name} ${item.keywords.join(' ')}`} onSelect={() => handleTheme(item.value)}>
                  <item.icon className="h-4 w-4" /><span>{item.name}</span>
                </CommandItem>
              ))}
            </CommandGroup>
            {exactCandidates.length > 0 && (
              <CommandGroup heading={t('knowledge.exactResults')}>
                {exactCandidates.map(candidate => (
                  <CommandItem key={candidate.key} value={`exact ${candidate.title} ${candidate.relativePath}`} onSelect={() => selectTab(candidateToOpenTab(candidate))}>
                    <FileText className="h-4 w-4" /><span>{candidate.title}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {indexedResults.length > 0 && (
              <CommandGroup heading={t('knowledge.indexedSearchResults')}>
                {indexedResults.map(result => {
                  const tab = searchResultToOpenTab(result)
                  if (result.vault_provenance && !tab) return null
                  if (!tab) return (
                    <CommandItem key={result.id} value={`search ${result.title}`} onSelect={handleSearch}>
                      <Search className="h-4 w-4" /><span>{result.title}</span>
                    </CommandItem>
                  )
                  return (
                    <CommandItem key={result.id} value={`indexed ${tab.title} ${tab.relativePath}`} onSelect={() => selectTab(tab)}>
                      <FileText className="h-4 w-4" /><span>{tab.title}</span>
                    </CommandItem>
                  )
                })}
              </CommandGroup>
            )}
            {query.trim().length >= 2 && (
              <CommandGroup heading={t('knowledge.semanticSearch')} forceMount>
                <CommandItem value={`semantic ${query}`} onSelect={indexed.runSemanticSearch} forceMount>
                  <Sparkles aria-hidden="true" className="h-4 w-4" />
                  <span>{t('knowledge.semanticSearchFor', { query })}</span>
                </CommandItem>
              </CommandGroup>
            )}
            {embeddingConfigurationError(indexed.semantic.error) && (
              <CommandGroup heading={t('knowledge.semanticUnavailable')} forceMount>
                <CommandItem value="configure embedding model" onSelect={() => handleNavigate('/settings/api-keys')} forceMount>
                  <Settings className="h-4 w-4" /><span>{t('knowledge.semanticUnavailable')}</span>
                </CommandItem>
              </CommandGroup>
            )}
            {semanticResults.length > 0 && (
              <CommandGroup heading={t('knowledge.semanticSearchResults')}>
                {semanticResults.map(result => {
                  const tab = searchResultToOpenTab(result)
                  if (result.vault_provenance && !tab) return null
                  if (!tab) return (
                    <CommandItem key={result.id} value={`semantic search ${result.title}`} onSelect={handleSearch}>
                      <Search className="h-4 w-4" /><span>{result.title}</span>
                    </CommandItem>
                  )
                  return (
                    <CommandItem key={result.id} value={`semantic result ${tab.title} ${tab.relativePath}`} onSelect={() => selectTab(tab)}>
                      <FileText className="h-4 w-4" /><span>{tab.title}</span>
                    </CommandItem>
                  )
                })}
              </CommandGroup>
            )}
            {query.trim() && hasCommandMatch && (
              <>
                <CommandSeparator />
                <CommandGroup heading={t('searchPage.orSearchKb')} forceMount>
                  <CommandItem value={`__search__ ${query}`} onSelect={handleSearch} forceMount>
                    <Search className="h-4 w-4" /><span>{t('searchPage.searchResultsFor').replace('{query}', query)}</span>
                  </CommandItem>
                  <CommandItem value={`__ask__ ${query}`} onSelect={handleAsk} forceMount>
                    <MessageCircleQuestion className="h-4 w-4" /><span>{t('searchPage.askAbout').replace('{query}', query)}</span>
                  </CommandItem>
                </CommandGroup>
              </>
            )}
          </>
        )}
      </CommandList>
    </CommandDialog>
  )
}

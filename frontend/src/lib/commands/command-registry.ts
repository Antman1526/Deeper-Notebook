import type { ResearchMode } from '@/lib/knowledge/research-modes'
import type { PodcastDestination } from '@/lib/podcasts/selection'

export type KnowledgeCommandId =
  | 'knowledge.view-reading'
  | 'knowledge.view-source'
  | 'knowledge.view-live-preview'
  | 'knowledge.view-graph'
  | 'knowledge.split-right'
  | 'knowledge.split-down'
  | 'knowledge.close-pane'
  | 'knowledge.close-tab'
  | 'knowledge.previous-tab'
  | 'knowledge.next-tab'
  | 'knowledge.scan-vault'
  | 'knowledge.focus-files'
  | 'knowledge.focus-pane'
  | 'knowledge.focus-links'
  | 'knowledge.overlay.today'
  | 'knowledge.overlay.unique'
  | 'knowledge.bookmark-current'
  | 'knowledge.open-bookmarks'
  | 'knowledge.random-note'
  | 'knowledge.open-workspaces'
  | 'knowledge.save-workspace-as'
  | 'knowledge.replace-workspace'
  | 'knowledge.toggle-metrics'
  | 'knowledge.mode.read'
  | 'knowledge.mode.write'
  | 'knowledge.mode.ask'
  | 'knowledge.mode.search'
  | 'knowledge.mode.graph'
  | 'knowledge.mode.podcast'
  | 'podcast.quick_from_selection'
  | 'podcast.open_studio_from_selection'

export type CommandScope = 'global' | 'knowledge'
export type CommandSafety = 'read' | 'workspace' | 'external-write'
export type KnowledgeCommandMode = 'global' | 'slash'

export interface KnowledgeCommandExecutionContext {
  activePaneId: string | null
  activeTabId: string | null
  paneCount: number
  selectedVaultId: string | null
  setViewMode: (mode: 'reading' | 'source' | 'live-preview' | 'graph') => void
  splitPane: (direction: 'horizontal' | 'vertical') => void
  closePane: () => void
  closeTab: () => void
  scanSelectedVault: (() => Promise<void>) | null
  openTodayOverlay: (() => Promise<void>) | null
  openUniqueOverlayDialog: (() => void) | null
  focusFileTree: (() => void) | null
  focusActivePane: (() => void) | null
  focusLinks: (() => void) | null
  moveTab: (offset: -1 | 1) => void
  bookmarkCurrentTarget: (() => void | Promise<void>) | null
  openBookmarks: (() => void) | null
  randomNote: (() => void | Promise<void>) | null
  openWorkspaces: (() => void) | null
  saveWorkspaceAs: (() => void) | null
  replaceWorkspace: (() => void) | null
  toggleMetrics: (() => void) | null
  researchModeAvailability: Record<ResearchMode, { available: boolean; reason: string | null }>
  openResearchMode: ((mode: ResearchMode) => void) | null
  /** Opens a transient review surface only; it cannot submit or mutate an external source. */
  openPodcastFromSelection: ((destination: PodcastDestination) => void) | null
}

export interface CommandDefinition {
  id: KnowledgeCommandId
  scope: CommandScope
  safety: CommandSafety
  labelKey: string
  aliases: string[]
  keywords: string[]
  isAvailable: (context: KnowledgeCommandExecutionContext) => boolean
  unavailableReasonKey?: string
  unavailableReason?: (context: KnowledgeCommandExecutionContext) => string | null
  execute: (context: KnowledgeCommandExecutionContext) => void | Promise<void>
}

const hasActiveTab = (context: KnowledgeCommandExecutionContext): boolean => (
  context.activeTabId !== null
)

const hasActivePane = (context: KnowledgeCommandExecutionContext): boolean => (
  context.activePaneId !== null
)

function isResearchModeAvailable(mode: ResearchMode, context: KnowledgeCommandExecutionContext): boolean {
  return context.openResearchMode !== null && context.researchModeAvailability[mode].available
}

function researchModeUnavailableReason(mode: ResearchMode, context: KnowledgeCommandExecutionContext): string | null {
  return context.researchModeAvailability[mode].reason
}

export const knowledgeCommandDefinitions: CommandDefinition[] = [
  {
    id: 'knowledge.view-reading',
    scope: 'knowledge',
    safety: 'read',
    labelKey: 'knowledge.commands.viewReading',
    aliases: ['reading', 'read'],
    keywords: ['view', 'reading'],
    isAvailable: hasActiveTab,
    unavailableReasonKey: 'knowledge.commands.requiresActiveTab',
    execute: context => context.setViewMode('reading'),
  },
  {
    id: 'knowledge.view-source',
    scope: 'knowledge',
    safety: 'read',
    labelKey: 'knowledge.commands.viewSource',
    aliases: ['source'],
    keywords: ['view', 'source', 'markdown'],
    isAvailable: hasActiveTab,
    unavailableReasonKey: 'knowledge.commands.requiresActiveTab',
    execute: context => context.setViewMode('source'),
  },
  {
    id: 'knowledge.view-live-preview',
    scope: 'knowledge',
    safety: 'read',
    labelKey: 'knowledge.commands.viewLivePreview',
    aliases: ['live preview', 'preview'],
    keywords: ['view', 'live', 'preview'],
    isAvailable: hasActiveTab,
    unavailableReasonKey: 'knowledge.commands.requiresActiveTab',
    execute: context => context.setViewMode('live-preview'),
  },
  {
    id: 'knowledge.view-graph',
    scope: 'knowledge',
    safety: 'read',
    labelKey: 'knowledge.commands.viewGraph',
    aliases: ['graph'],
    keywords: ['view', 'graph', 'links'],
    isAvailable: hasActiveTab,
    unavailableReasonKey: 'knowledge.commands.requiresActiveTab',
    execute: context => context.setViewMode('graph'),
  },
  {
    id: 'knowledge.split-right',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.splitRight',
    aliases: ['split right'],
    keywords: ['split', 'right', 'pane'],
    isAvailable: hasActivePane,
    unavailableReasonKey: 'knowledge.commands.requiresActivePane',
    execute: context => context.splitPane('horizontal'),
  },
  {
    id: 'knowledge.split-down',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.splitDown',
    aliases: ['split down'],
    keywords: ['split', 'down', 'pane'],
    isAvailable: hasActivePane,
    unavailableReasonKey: 'knowledge.commands.requiresActivePane',
    execute: context => context.splitPane('vertical'),
  },
  {
    id: 'knowledge.close-pane',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.closePane',
    aliases: ['close pane'],
    keywords: ['close', 'pane'],
    isAvailable: context => context.paneCount > 1,
    unavailableReasonKey: 'knowledge.commands.requiresMultiplePanes',
    execute: context => context.closePane(),
  },
  {
    id: 'knowledge.close-tab',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.closeTab',
    aliases: ['close tab'],
    keywords: ['close', 'tab'],
    isAvailable: hasActiveTab,
    unavailableReasonKey: 'knowledge.commands.requiresActiveTab',
    execute: context => context.closeTab(),
  },
  {
    id: 'knowledge.previous-tab',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.previousTab',
    aliases: ['previous tab', 'prev tab'],
    keywords: ['previous', 'back', 'tab'],
    isAvailable: hasActiveTab,
    unavailableReasonKey: 'knowledge.commands.requiresActiveTab',
    execute: context => context.moveTab(-1),
  },
  {
    id: 'knowledge.next-tab',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.nextTab',
    aliases: ['next tab'],
    keywords: ['next', 'forward', 'tab'],
    isAvailable: hasActiveTab,
    unavailableReasonKey: 'knowledge.commands.requiresActiveTab',
    execute: context => context.moveTab(1),
  },
  {
    id: 'knowledge.scan-vault',
    scope: 'knowledge',
    safety: 'read',
    labelKey: 'knowledge.commands.scanVault',
    aliases: ['scan vault'],
    keywords: ['scan', 'vault', 'index'],
    isAvailable: context => (
      context.selectedVaultId !== null && context.scanSelectedVault !== null
    ),
    unavailableReasonKey: 'knowledge.commands.requiresSelectedVault',
    execute: context => context.scanSelectedVault!(),
  },
  {
    id: 'knowledge.overlay.today',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.overlay.today',
    aliases: ['today', 'daily note'],
    keywords: ['overlay', 'today', 'daily', 'note'],
    isAvailable: context => context.openTodayOverlay !== null,
    execute: context => context.openTodayOverlay!(),
  },
  {
    id: 'knowledge.overlay.unique',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.overlay.newUnique',
    aliases: ['new unique note', 'unique note'],
    keywords: ['overlay', 'new', 'unique', 'note'],
    isAvailable: context => context.openUniqueOverlayDialog !== null,
    execute: context => context.openUniqueOverlayDialog!(),
  },
  {
    id: 'knowledge.focus-files',
    scope: 'knowledge',
    safety: 'read',
    labelKey: 'knowledge.commands.focusFiles',
    aliases: ['focus files', 'files'],
    keywords: ['focus', 'files', 'file tree'],
    isAvailable: context => context.focusFileTree !== null,
    unavailableReasonKey: 'knowledge.commands.requiresFileTree',
    execute: context => context.focusFileTree!(),
  },
  {
    id: 'knowledge.focus-pane',
    scope: 'knowledge',
    safety: 'read',
    labelKey: 'knowledge.commands.focusPane',
    aliases: ['focus pane'],
    keywords: ['focus', 'pane', 'editor'],
    isAvailable: context => (
      context.activePaneId !== null && context.focusActivePane !== null
    ),
    unavailableReasonKey: 'knowledge.commands.requiresActivePane',
    execute: context => context.focusActivePane!(),
  },
  {
    id: 'knowledge.focus-links',
    scope: 'knowledge',
    safety: 'read',
    labelKey: 'knowledge.commands.focusLinks',
    aliases: ['focus links', 'links'],
    keywords: ['focus', 'links', 'backlinks'],
    isAvailable: context => context.focusLinks !== null,
    unavailableReasonKey: 'knowledge.commands.requiresLinks',
    execute: context => context.focusLinks!(),
  },
  {
    id: 'knowledge.bookmark-current',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.bookmarkCurrent',
    aliases: ['bookmark current', 'bookmark target'],
    keywords: ['bookmark', 'current', 'target'],
    isAvailable: context => hasActiveTab(context) && context.bookmarkCurrentTarget !== null,
    unavailableReasonKey: 'knowledge.commands.requiresActiveTab',
    execute: context => context.bookmarkCurrentTarget!(),
  },
  {
    id: 'knowledge.open-bookmarks',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.openBookmarks',
    aliases: ['bookmarks'],
    keywords: ['open', 'bookmarks'],
    isAvailable: context => context.openBookmarks !== null,
    execute: context => context.openBookmarks!(),
  },
  {
    id: 'knowledge.random-note',
    scope: 'knowledge',
    safety: 'read',
    labelKey: 'knowledge.commands.randomNote',
    aliases: ['random note'],
    keywords: ['random', 'note'],
    isAvailable: context => context.randomNote !== null,
    execute: context => context.randomNote!(),
  },
  {
    id: 'knowledge.open-workspaces',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.openWorkspaces',
    aliases: ['workspaces'],
    keywords: ['open', 'workspaces'],
    isAvailable: context => context.openWorkspaces !== null,
    execute: context => context.openWorkspaces!(),
  },
  {
    id: 'knowledge.save-workspace-as',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.saveWorkspaceAs',
    aliases: ['save workspace'],
    keywords: ['save', 'workspace', 'as'],
    isAvailable: context => context.saveWorkspaceAs !== null,
    execute: context => context.saveWorkspaceAs!(),
  },
  {
    id: 'knowledge.replace-workspace',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.replaceWorkspace',
    aliases: ['replace workspace'],
    keywords: ['replace', 'workspace'],
    isAvailable: context => context.replaceWorkspace !== null,
    execute: context => context.replaceWorkspace!(),
  },
  {
    id: 'knowledge.toggle-metrics',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.toggleMetrics',
    aliases: ['metrics'],
    keywords: ['toggle', 'metrics', 'words', 'characters'],
    isAvailable: context => context.toggleMetrics !== null,
    execute: context => context.toggleMetrics!(),
  },
  {
    id: 'podcast.quick_from_selection',
    scope: 'knowledge',
    // This changes only ephemeral app UI state. Selection resolution may read
    // external evidence later, but it grants no external mutation capability.
    safety: 'workspace',
    labelKey: 'podcasts.generateBtn',
    aliases: ['quick podcast', 'turn note into podcast'],
    keywords: ['podcast', 'quick', 'audio', 'current note'],
    isAvailable: context => context.openPodcastFromSelection !== null,
    unavailableReasonKey: 'knowledge.commands.requiresActiveTab',
    execute: context => context.openPodcastFromSelection!('quick'),
  },
  {
    id: 'podcast.open_studio_from_selection',
    scope: 'knowledge',
    safety: 'workspace',
    labelKey: 'knowledge.commands.modePodcast',
    aliases: ['podcast studio', 'open studio from current note'],
    keywords: ['podcast', 'studio', 'audio', 'current note'],
    isAvailable: context => context.openPodcastFromSelection !== null,
    unavailableReasonKey: 'knowledge.commands.requiresActiveTab',
    execute: context => context.openPodcastFromSelection!('studio'),
  },
  ...([
    ['read', 'knowledge.commands.modeRead', ['read'], ['mode', 'read']],
    ['write', 'knowledge.commands.modeWrite', ['write'], ['mode', 'write', 'overlay']],
    ['ask', 'knowledge.commands.modeAsk', ['ask'], ['mode', 'ask', 'research']],
    ['search', 'knowledge.commands.modeSearch', ['search'], ['mode', 'search']],
    ['graph', 'knowledge.commands.modeGraph', ['graph'], ['mode', 'graph', 'connections']],
    ['podcast', 'knowledge.commands.modePodcast', ['podcast'], ['mode', 'podcast', 'audio']],
  ] as const).map(([mode, labelKey, aliases, keywords]): CommandDefinition => ({
    id: `knowledge.mode.${mode}` as KnowledgeCommandId,
    scope: 'knowledge',
    // A mode switch changes only the app-owned workspace document.  It never
    // grants an external source mutation capability.
    safety: 'workspace',
    labelKey,
    aliases: [...aliases],
    keywords: [...keywords],
    isAvailable: context => isResearchModeAvailable(mode, context),
    unavailableReason: context => researchModeUnavailableReason(mode, context),
    execute: context => context.openResearchMode!(mode),
  })),
]

export function availableKnowledgeCommands(
  context: KnowledgeCommandExecutionContext,
  mode: KnowledgeCommandMode,
): Array<Omit<CommandDefinition, 'isAvailable' | 'unavailableReason'> & { available: boolean; unavailableReason: string | null }> {
  return knowledgeCommandDefinitions
    .filter(command => mode !== 'slash' || command.safety !== 'external-write')
    .map(({ isAvailable, unavailableReason, ...command }) => ({
      ...command,
      available: isAvailable(context),
      unavailableReason: unavailableReason?.(context) ?? null,
    }))
}

export function executeKnowledgeCommand(
  id: KnowledgeCommandId,
  context: KnowledgeCommandExecutionContext,
): Promise<boolean> {
  const command = knowledgeCommandDefinitions.find(candidate => candidate.id === id)
  if (
    !command
    || command.safety === 'external-write'
    || !command.isAvailable(context)
  ) {
    return Promise.resolve(false)
  }
  return Promise.resolve()
    .then(() => command.execute(context))
    .then(() => true)
}

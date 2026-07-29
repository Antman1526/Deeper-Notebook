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
  focusFileTree: (() => void) | null
  focusActivePane: (() => void) | null
  focusLinks: (() => void) | null
  moveTab: (offset: -1 | 1) => void
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
  execute: (context: KnowledgeCommandExecutionContext) => void | Promise<void>
}

const hasActiveTab = (context: KnowledgeCommandExecutionContext): boolean => (
  context.activeTabId !== null
)

const hasActivePane = (context: KnowledgeCommandExecutionContext): boolean => (
  context.activePaneId !== null
)

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
]

export function availableKnowledgeCommands(
  context: KnowledgeCommandExecutionContext,
  mode: KnowledgeCommandMode,
): Array<Omit<CommandDefinition, 'isAvailable'> & { available: boolean }> {
  return knowledgeCommandDefinitions
    .filter(command => mode !== 'slash' || command.safety !== 'external-write')
    .map(({ isAvailable, ...command }) => ({
      ...command,
      available: isAvailable(context),
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

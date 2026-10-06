import type { TFunction } from 'i18next'

import type { KnowledgeTab } from '@/lib/api/knowledge-workspace'

export type ResearchMode = NonNullable<KnowledgeTab['mode']>
export type KnowledgeTabTarget = NonNullable<KnowledgeTab['target']>

export type ResearchModeDescriptor = {
  id: ResearchMode
  labelKey:
    | 'knowledge.commands.modeRead'
    | 'knowledge.commands.modeWrite'
    | 'knowledge.commands.modeAsk'
    | 'knowledge.commands.modeSearch'
    | 'knowledge.commands.modeGraph'
    | 'knowledge.commands.modePodcast'
  shortcut: '1' | '2' | '3' | '4' | '5' | '6'
  targetKind: KnowledgeTabTarget['kind']
  requiresDocument: boolean
}

export const RESEARCH_MODE_DESCRIPTORS: Record<ResearchMode, ResearchModeDescriptor> = {
  read: { id: 'read', labelKey: 'knowledge.commands.modeRead', shortcut: '1', targetKind: 'document', requiresDocument: true },
  write: { id: 'write', labelKey: 'knowledge.commands.modeWrite', shortcut: '2', targetKind: 'document', requiresDocument: true },
  ask: { id: 'ask', labelKey: 'knowledge.commands.modeAsk', shortcut: '3', targetKind: 'ask', requiresDocument: false },
  search: { id: 'search', labelKey: 'knowledge.commands.modeSearch', shortcut: '4', targetKind: 'search', requiresDocument: false },
  graph: { id: 'graph', labelKey: 'knowledge.commands.modeGraph', shortcut: '5', targetKind: 'graph', requiresDocument: false },
  podcast: { id: 'podcast', labelKey: 'knowledge.commands.modePodcast', shortcut: '6', targetKind: 'podcast', requiresDocument: false },
}

export const RESEARCH_MODE_ICON_KEYS: Record<ResearchMode, string> = {
  read: 'book-open',
  write: 'file-pen-line',
  ask: 'message-circle-question',
  search: 'search',
  graph: 'network',
  podcast: 'podcast',
}

type LocalResearchHealth = {
  isLoading?: boolean
  isError?: boolean
  error?: { message?: string } | null
  data?: {
    models?: Array<{
      credential_id?: string | null
      status?: 'healthy' | 'unhealthy' | 'not_configured' | 'unknown'
      detail?: string | null
    }>
  }
}

export function getLocalResearchReadinessReason(
  health: LocalResearchHealth,
  chatModel: { id: string; credentialId: string | null } | null,
  t: TFunction,
): string | null {
  if (health.isLoading) return t('knowledge.researchModes.readinessLoading')
  if (health.isError) return health.error?.message || t('knowledge.researchModes.readinessUnavailable')
  if (!chatModel) return t('knowledge.researchModes.noChatModel')
  if (!chatModel.credentialId) {
    return t('knowledge.researchModes.chatModelNotLinked')
  }
  const healthEntry = health.data?.models?.find(
    (model) => model.credential_id === chatModel.credentialId,
  )
  if (healthEntry?.status === 'healthy') return null
  return healthEntry?.detail
    || t('knowledge.researchModes.chatModelUnavailable', { id: chatModel.id })
}

type ResearchModeAvailabilityContext = {
  target?: Pick<KnowledgeTabTarget, 'kind'> & { authority?: 'external-vault' | 'overlay' }
  askReadinessReason?: string | null
  t: TFunction
}

export function getResearchModeAvailability(
  mode: ResearchMode,
  { target, askReadinessReason = null, t }: ResearchModeAvailabilityContext,
): { available: boolean; reason: string | null } {
  const descriptor = RESEARCH_MODE_DESCRIPTORS[mode]
  if (!target || target.kind !== descriptor.targetKind) {
    return { available: false, reason: t('knowledge.researchModes.requiresTarget', { kind: descriptor.targetKind }) }
  }
  if (mode === 'write' && target.authority === 'external-vault') {
    return { available: false, reason: t('knowledge.researchModes.externalReadOnly') }
  }
  if (mode === 'ask' && askReadinessReason) {
    return { available: false, reason: askReadinessReason }
  }
  return { available: true, reason: null }
}

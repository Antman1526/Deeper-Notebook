import type { KnowledgeTab } from '@/lib/api/knowledge-workspace'

export type ResearchMode = NonNullable<KnowledgeTab['mode']>
export type KnowledgeTabTarget = NonNullable<KnowledgeTab['target']>

export type ResearchModeDescriptor = {
  id: ResearchMode
  label: 'Read' | 'Write' | 'Ask' | 'Search' | 'Graph' | 'Podcast'
  shortcut: '1' | '2' | '3' | '4' | '5' | '6'
  targetKind: KnowledgeTabTarget['kind']
  requiresDocument: boolean
}

export const RESEARCH_MODE_DESCRIPTORS: Record<ResearchMode, ResearchModeDescriptor> = {
  read: { id: 'read', label: 'Read', shortcut: '1', targetKind: 'document', requiresDocument: true },
  write: { id: 'write', label: 'Write', shortcut: '2', targetKind: 'document', requiresDocument: true },
  ask: { id: 'ask', label: 'Ask', shortcut: '3', targetKind: 'ask', requiresDocument: false },
  search: { id: 'search', label: 'Search', shortcut: '4', targetKind: 'search', requiresDocument: false },
  graph: { id: 'graph', label: 'Graph', shortcut: '5', targetKind: 'graph', requiresDocument: false },
  podcast: { id: 'podcast', label: 'Podcast', shortcut: '6', targetKind: 'podcast', requiresDocument: false },
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
): string | null {
  if (health.isLoading) return 'Local model readiness is loading'
  if (health.isError) return health.error?.message || 'Local model readiness is unavailable'
  if (!chatModel) return 'No local research chat model is configured'
  if (!chatModel.credentialId) {
    return 'Configured chat model is not linked to a local sidecar'
  }
  const healthEntry = health.data?.models?.find(
    (model) => model.credential_id === chatModel.credentialId,
  )
  if (healthEntry?.status === 'healthy') return null
  return healthEntry?.detail
    || `Configured chat model ${chatModel.id} is unavailable`
}

type ResearchModeAvailabilityContext = {
  target?: Pick<KnowledgeTabTarget, 'kind'> & { authority?: 'external-vault' | 'overlay' }
  askReadinessReason?: string | null
}

export function getResearchModeAvailability(
  mode: ResearchMode,
  { target, askReadinessReason = null }: ResearchModeAvailabilityContext,
): { available: boolean; reason: string | null } {
  const descriptor = RESEARCH_MODE_DESCRIPTORS[mode]
  if (!target || target.kind !== descriptor.targetKind) {
    return { available: false, reason: `Requires a ${descriptor.targetKind} target` }
  }
  if (mode === 'write' && target.authority === 'external-vault') {
    return { available: false, reason: 'External source — read only' }
  }
  if (mode === 'ask' && askReadinessReason) {
    return { available: false, reason: askReadinessReason }
  }
  return { available: true, reason: null }
}

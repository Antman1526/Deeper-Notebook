'use client'

import { useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  Bot,
  CheckCircle2,
  Cloud,
  Database,
  HelpCircle,
  Lock,
  Plug,
  Radio,
  ShieldCheck,
  WifiOff,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { McpToolCall, NotebookChatMessage } from '@/lib/types/api'

interface RunTimelineContextStats {
  sourcesInsights: number
  sourcesFull: number
  notesCount: number
  tokenCount?: number
  charCount?: number
}

interface CachedRunSelection {
  selected_provider?: string | null
  selected_model_id?: string | null
  privacy_gated?: boolean | null
  privacy_categories?: string[] | null
  agent_state?: string | null
  offline_fallback?: {
    to_model_name?: string | null
    reason?: string
  } | null
}

export interface RunTimelineProps {
  messages: NotebookChatMessage[]
  isStreaming: boolean
  contextStats?: RunTimelineContextStats
  currentModel?: string
  disabledMcpServers?: string[]
}

function latestAiMessage(messages: NotebookChatMessage[]) {
  return [...messages].reverse().find((message) => message.type === 'ai')
}

function formatCount(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`
}

function contextSummary(stats?: RunTimelineContextStats) {
  if (!stats) return 'No context profile yet'
  const parts = [
    formatCount(stats.sourcesInsights, 'insight source'),
    formatCount(stats.sourcesFull, 'full source'),
    formatCount(stats.notesCount, 'note'),
  ]
  if (typeof stats.tokenCount === 'number' && stats.tokenCount > 0) {
    parts.push(`${stats.tokenCount.toLocaleString()} tokens`)
  }
  return parts.join(' / ')
}

function routeSummary(selection?: CachedRunSelection, currentModel?: string) {
  if (selection?.offline_fallback) {
    return `offline fallback -> ${selection.offline_fallback.to_model_name || 'local model'}`
  }
  if (selection?.selected_provider) {
    return `${selection.selected_provider}${selection.selected_model_id ? ` / ${selection.selected_model_id}` : ''}`
  }
  if (currentModel) return `manual / ${currentModel}`
  return 'auto route pending'
}

function privacySummary(selection?: CachedRunSelection) {
  if (selection?.privacy_gated) {
    const categories = selection.privacy_categories?.length
      ? ` (${selection.privacy_categories.join(', ')})`
      : ''
    return `kept local${categories}`
  }
  return 'no gate triggered'
}

function agentSummary(selection?: CachedRunSelection, isStreaming?: boolean) {
  if (isStreaming) return 'working'
  return selection?.agent_state || 'complete'
}

export function RunTimeline({
  messages,
  isStreaming,
  contextStats,
  currentModel,
  disabledMcpServers = [],
}: RunTimelineProps) {
  const queryClient = useQueryClient()
  const latestAi = useMemo(() => latestAiMessage(messages), [messages])
  const runSelection = latestAi
    ? queryClient.getQueryData<CachedRunSelection>([
        'chat',
        'selected-provider',
        latestAi.id,
      ])
    : undefined
  const mcpCalls = latestAi
    ? queryClient.getQueryData<McpToolCall[]>(['mcp', 'tool-calls', latestAi.id]) ?? []
    : []
  const activeStatus = isStreaming ? 'Streaming response' : latestAi ? 'Last run complete' : 'Ready'
  const disabledToolLabel = disabledMcpServers.length > 0
    ? `${disabledMcpServers.length} disabled`
    : 'all available'

  const steps = [
    {
      label: 'Context built',
      value: contextSummary(contextStats),
      Icon: Database,
      active: false,
    },
    {
      label: 'Model route',
      value: routeSummary(runSelection, currentModel),
      Icon: runSelection?.offline_fallback ? WifiOff : runSelection?.selected_provider === 'cloud' ? Cloud : Bot,
      active: isStreaming,
    },
    {
      label: 'MCP tools',
      value: `${formatCount(mcpCalls.length, 'call')} / ${disabledToolLabel}`,
      Icon: Plug,
      active: isStreaming && mcpCalls.length > 0,
    },
    {
      label: 'Privacy gate',
      value: privacySummary(runSelection),
      Icon: runSelection?.privacy_gated ? ShieldCheck : Lock,
      active: Boolean(runSelection?.privacy_gated),
    },
    {
      label: 'Agent state',
      value: agentSummary(runSelection, isStreaming),
      Icon: runSelection?.agent_state === 'clarify' ? HelpCircle : isStreaming ? Radio : CheckCircle2,
      active: isStreaming,
    },
  ]

  return (
    <section
      aria-label="Run timeline"
      className="border-b bg-[var(--onp-surface-raised)] px-4 py-3"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" aria-hidden="true" />
          <div>
            <div className="text-sm font-semibold leading-none">Run timeline</div>
            <div className="mt-1 text-xs text-muted-foreground">{activeStatus}</div>
          </div>
        </div>
        <Badge
          variant="outline"
          className={cn(
            'bg-background/80 text-[0.7rem]',
            isStreaming && 'border-[var(--onp-info)] text-[var(--onp-info)]',
          )}
        >
          {isStreaming ? 'running' : 'idle'}
        </Badge>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {steps.map(({ label, value, Icon, active }) => (
          <div
            key={label}
            className={cn(
              'min-w-0 rounded-md border bg-background/80 px-2.5 py-2',
              active && 'border-[var(--onp-accent-strong)] bg-[var(--onp-accent-soft)]',
            )}
          >
            <div className="flex items-center gap-1.5 text-[0.7rem] font-medium text-muted-foreground">
              <Icon className="h-3.5 w-3.5 flex-none" aria-hidden="true" />
              <span>{label}</span>
            </div>
            <div className="mt-1 truncate text-xs font-medium" title={value}>
              {value}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

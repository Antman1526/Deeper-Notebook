'use client'

import { Fragment, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  Bot,
  CheckCircle2,
  ChevronDown,
  Cloud,
  Database,
  HelpCircle,
  Lock,
  Plug,
  Radio,
  ShieldCheck,
  WifiOff,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
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
  const detailsId = useId()
  const [open, setOpen] = useState(false)
  const detailsRef = useRef<HTMLDListElement>(null)
  // Opened under the last answer, the facts landed below the fold. Scroll only the
  // chat's own viewport: scrollIntoView also scrolls the page canvas (Phase 2a).
  useEffect(() => {
    if (!open) return
    const details = detailsRef.current
    const viewport = details?.closest<HTMLElement>('[data-radix-scroll-area-viewport]')
    if (!details || !viewport) return
    const overflow = details.getBoundingClientRect().bottom - viewport.getBoundingClientRect().bottom
    if (overflow > 0) viewport.scrollTop += overflow + 8
  }, [open])
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
  const disabledToolLabel = disabledMcpServers.length > 0
    ? `${disabledMcpServers.length} disabled`
    : 'all available'

  // v0.8.130 — Phase 2c: the five-card "Run timeline · idle" panel sat above every chat,
  // empty ones included. Now: nothing before the first run, one status line while a
  // response streams, and the facts behind a collapsed "Run details" under the answer.
  if (!isStreaming && !latestAi) return null

  if (isStreaming) {
    return (
      <div role="status" className="flex items-center gap-2 text-xs text-muted-foreground">
        <Radio className="h-3.5 w-3.5 flex-none text-primary motion-safe:animate-pulse" aria-hidden="true" />
        <span>Streaming response</span>
        <span aria-hidden="true">·</span>
        <span className="min-w-0 truncate">{routeSummary(runSelection, currentModel)}</span>
      </div>
    )
  }

  const steps = [
    { label: 'Context built', value: contextSummary(contextStats), Icon: Database },
    {
      label: 'Model route',
      value: routeSummary(runSelection, currentModel),
      Icon: runSelection?.offline_fallback ? WifiOff : runSelection?.selected_provider === 'cloud' ? Cloud : Bot,
    },
    { label: 'MCP tools', value: `${formatCount(mcpCalls.length, 'call')} / ${disabledToolLabel}`, Icon: Plug },
    { label: 'Privacy gate', value: privacySummary(runSelection), Icon: runSelection?.privacy_gated ? ShieldCheck : Lock },
    {
      label: 'Agent state',
      value: agentSummary(runSelection, false),
      Icon: runSelection?.agent_state === 'clarify' ? HelpCircle : CheckCircle2,
    },
  ]

  return (
    <div className="text-xs">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-expanded={open}
        aria-controls={detailsId}
        onClick={() => setOpen((value) => !value)}
        className="h-auto gap-1.5 px-2 py-1 text-xs font-normal text-muted-foreground hover:text-foreground"
      >
        <Activity className="h-3.5 w-3.5" aria-hidden="true" />
        Run details
        <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} aria-hidden="true" />
      </Button>
      <dl
        ref={detailsRef}
        id={detailsId}
        hidden={!open}
        className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 rounded-xl bg-muted/50 px-3 py-2.5"
      >
        {steps.map(({ label, value, Icon }) => (
          <Fragment key={label}>
            <dt className="flex items-center gap-1.5 text-muted-foreground">
              <Icon className="h-3.5 w-3.5 flex-none" aria-hidden="true" />
              {label}
            </dt>
            <dd className="min-w-0 [overflow-wrap:anywhere]">{value}</dd>
          </Fragment>
        ))}
      </dl>
    </div>
  )
}

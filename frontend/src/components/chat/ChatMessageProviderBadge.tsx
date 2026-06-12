'use client'

/**
 * ChatMessageProviderBadge.tsx — v0.8.35c
 *
 * Small "local" / "cloud" chip rendered next to an AI message in the
 * notebook chat view, indicating which side of the smart router served
 * that turn.
 *
 * Data flow:
 *   /chat/stream `done` NDJSON event carries
 *     { selected_provider: 'local'|'cloud'|null,
 *       selected_model_id: string|null }
 *   useNotebookChat stashes it in TanStack Query cache under
 *     ['chat', 'selected-provider', messageId]
 *   This component reads from that cache by messageId — no prop drilling
 *   through ChatPanel.
 *
 * The badge intentionally renders NOTHING when:
 *   - no cache entry exists (old sessions / source-chat / streaming
 *     turn pre-`done` event)
 *   - the cache entry has `selected_provider === null` (smart routing
 *     was off / explicit model_override path)
 *
 * That way enabling smart routing later doesn't retro-label
 * pre-existing messages with a misleading badge.
 *
 * Companion to:
 *   - api/routers/chat.py `_stream_chat_events` done event
 *   - open_notebook/ai/provision.py `provision_langchain_chat_model`
 *   - scripts/verify-chat-platform.sh Steps 4+5
 */

import React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Cloud, MonitorCog, WifiOff } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useTranslation } from '@/lib/hooks/use-translation'

export interface ChatMessageProviderBadgeProps {
  /** AI message ID to look up the routing decision for. */
  messageId: string
}

type CachedSelection = {
  selected_provider: string | null
  selected_model_id: string | null
  // v0.8.68 — offline gate substitution info (null when the gate didn't act).
  offline_fallback?: {
    to_model_name?: string | null
    reason?: string
  } | null
}

export function ChatMessageProviderBadge({
  messageId,
}: ChatMessageProviderBadgeProps) {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  // Cache-only read — we never trigger a fetch, we just look up what
  // useNotebookChat already stashed on the done event. Reading via
  // getQueryData (not useQuery) avoids forcing an unused query
  // subscription per AI message — every notebook chat has potentially
  // dozens of these badges and a useQuery per badge is overkill.
  const cached = queryClient.getQueryData<CachedSelection>([
    'chat',
    'selected-provider',
    messageId,
  ])

  // v0.8.68 — the offline pill takes precedence over the routing badge:
  // when the offline gate substituted a local model, "answered offline
  // with X" is strictly more informative than the plain "local" chip.
  if (cached?.offline_fallback) {
    const model =
      cached.offline_fallback.to_model_name ??
      t('network.localModelFallbackName', {
        defaultValue: 'local model',
      })
    return (
      <Badge
        variant="outline"
        className="text-xs gap-1 font-normal border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400"
        data-testid="provider-badge-offline-fallback"
      >
        <WifiOff className="h-3 w-3" />
        {t('network.answeredWithLocal', {
          defaultValue: 'Answered with {{model}} (offline)',
          model,
        })}
      </Badge>
    )
  }

  if (!cached || !cached.selected_provider) {
    return null
  }

  const provider = cached.selected_provider
  // i18n keys live under `chat.providerBadge.*`. Fallback to the raw
  // provider string when the key is missing so we never render an
  // empty pill that confuses the user.
  const label =
    provider === 'local'
      ? t('chat.providerBadge.local', { defaultValue: 'local' })
      : provider === 'cloud'
        ? t('chat.providerBadge.cloud', { defaultValue: 'cloud' })
        : provider
  const Icon = provider === 'local' ? MonitorCog : Cloud
  const tooltipText = cached.selected_model_id
    ? t('chat.providerBadge.tooltipWithModel', {
        defaultValue: 'Served by the {{provider}} model: {{model}}',
        provider,
        model: cached.selected_model_id,
      })
    : t('chat.providerBadge.tooltip', {
        defaultValue: 'Served by the {{provider}} model',
        provider,
      })

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className="text-xs gap-1 font-normal cursor-help"
          data-testid={`provider-badge-${provider}`}
        >
          <Icon className="h-3 w-3" />
          {label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="top">{tooltipText}</TooltipContent>
    </Tooltip>
  )
}

export default ChatMessageProviderBadge

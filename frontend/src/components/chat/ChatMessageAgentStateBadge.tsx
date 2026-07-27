'use client'

/**
 * ChatMessageAgentStateBadge.tsx — v0.8.62 (Phase 5.3c UI)
 *
 * Small chip rendered next to an AI message when the agent-FSM
 * (backend v0.8.60, DEEPER_NOTEBOOK_AGENT_FSM) reports a non-"complete" terminal
 * state for the chat tool loop:
 *   - "clarify"   → the model PAUSED to ask the user a question
 *   - "truncated" → the loop hit the tool-iteration cap (answer may be
 *                   incomplete)
 *
 * Data flow mirrors ChatMessageProviderBadge / ChatMessagePrivacyBadge:
 *   /chat/stream `done` event carries `agent_state`; useNotebookChat
 *   stashes it in the TanStack cache under
 *   ['chat', 'selected-provider', messageId]; this component reads it.
 *
 * Renders NOTHING for "complete", null, or no cache entry — so the FSM
 * being off (the default) never adds chrome to a message.
 */

import React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { HelpCircle, ScissorsLineDashed } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useTranslation } from '@/lib/hooks/use-translation'

export interface ChatMessageAgentStateBadgeProps {
  /** AI message ID to look up the agent-FSM terminal state for. */
  messageId: string
}

type CachedSelection = {
  agent_state?: string | null
}

export function ChatMessageAgentStateBadge({
  messageId,
}: ChatMessageAgentStateBadgeProps) {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  const cached = queryClient.getQueryData<CachedSelection>([
    'chat',
    'selected-provider',
    messageId,
  ])

  const state = cached?.agent_state
  if (state !== 'clarify' && state !== 'truncated') {
    return null
  }

  const isClarify = state === 'clarify'
  const Icon = isClarify ? HelpCircle : ScissorsLineDashed
  const label = isClarify
    ? t('chat.agentState.clarifyLabel', { defaultValue: 'Needs your input' })
    : t('chat.agentState.truncatedLabel', { defaultValue: 'Truncated' })
  const tooltipText = isClarify
    ? t('chat.agentState.clarifyTooltip', {
        defaultValue:
          'The assistant paused to ask you a question rather than finishing.',
      })
    : t('chat.agentState.truncatedTooltip', {
        defaultValue:
          'The assistant hit the tool-call limit — the answer may be incomplete.',
      })

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className="text-xs gap-1 font-normal cursor-help"
          data-testid={`agent-state-badge-${state}`}
        >
          <Icon className="h-3 w-3" />
          {label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="top">{tooltipText}</TooltipContent>
    </Tooltip>
  )
}

export default ChatMessageAgentStateBadge

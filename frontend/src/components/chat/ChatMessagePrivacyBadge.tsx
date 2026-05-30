'use client'

/**
 * ChatMessagePrivacyBadge.tsx — v0.8.61 / interactive review sheet v0.8.63
 *
 * Small "🛡 On-device" chip rendered next to an AI message when the
 * fail-closed privacy gate (backend v0.8.51/v0.8.57/v0.8.58) kept the turn
 * on the local model because sensitive content was detected.
 *
 * Clicking the chip opens a small review popover listing the detected
 * category LABELS (e.g. "email, person_name" — labels only; the backend
 * never sends the matched secret values) and an explanation. When an
 * `onReask` callback is provided (notebook chat), the popover also offers a
 * "Re-ask allowing cloud" action — explicit user consent that re-sends the
 * question with the privacy gate bypassed for that one turn (v0.8.63).
 *
 * Data flow mirrors ChatMessageProviderBadge (v0.8.35c): reads
 * privacy_gated / privacy_categories from the TanStack cache entry
 * useNotebookChat stashes on the `done` event. Renders NOTHING unless
 * `privacy_gated === true`.
 */

import React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ShieldCheck, CloudUpload } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import { useTranslation } from '@/lib/hooks/use-translation'

export interface ChatMessagePrivacyBadgeProps {
  /** AI message ID to look up the privacy-gate decision for. */
  messageId: string
  /**
   * Optional "Re-ask allowing cloud" handler (notebook chat). When provided
   * AND the gate fired, the review popover offers a button that calls this —
   * the caller re-sends the question with the gate bypassed. Omitted (e.g.
   * source chat) → the popover is review-only.
   */
  onReask?: () => void
}

type CachedSelection = {
  privacy_gated?: boolean | null
  privacy_categories?: string[] | null
}

export function ChatMessagePrivacyBadge({
  messageId,
  onReask,
}: ChatMessagePrivacyBadgeProps) {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  const cached = queryClient.getQueryData<CachedSelection>([
    'chat',
    'selected-provider',
    messageId,
  ])

  if (!cached || cached.privacy_gated !== true) {
    return null
  }

  const categories = cached.privacy_categories ?? []
  const label = t('chat.privacyBadge.label', { defaultValue: 'On-device' })
  const heading = t('chat.privacyBadge.heading', {
    defaultValue: 'Kept on your device',
  })
  const explanation = categories.length
    ? t('chat.privacyBadge.explanationWithCategories', {
        defaultValue:
          'This turn looked like it contained sensitive data ({{categories}}), '
          + 'so it was answered by the local model instead of being sent to the cloud.',
        categories: categories.join(', '),
      })
    : t('chat.privacyBadge.explanation', {
        defaultValue:
          'This turn was answered by the local model instead of being sent '
          + 'to the cloud, to keep sensitive data on your device.',
      })

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Badge
          variant="outline"
          className="text-xs gap-1 font-normal cursor-pointer"
          data-testid="privacy-badge"
        >
          <ShieldCheck className="h-3 w-3" />
          {label}
        </Badge>
      </PopoverTrigger>
      <PopoverContent side="top" className="w-72 text-sm space-y-2">
        <div className="font-medium">{heading}</div>
        <p className="text-muted-foreground text-xs">{explanation}</p>
        {categories.length > 0 && (
          <div className="flex flex-wrap gap-1" data-testid="privacy-categories">
            {categories.map((c) => (
              <Badge key={c} variant="secondary" className="text-[10px] font-normal">
                {c}
              </Badge>
            ))}
          </div>
        )}
        {onReask && (
          <Button
            size="sm"
            variant="outline"
            className="w-full mt-1 gap-1"
            data-testid="privacy-reask"
            onClick={onReask}
          >
            <CloudUpload className="h-3 w-3" />
            {t('chat.privacyBadge.reask', {
              defaultValue: 'Re-ask allowing cloud',
            })}
          </Button>
        )}
      </PopoverContent>
    </Popover>
  )
}

export default ChatMessagePrivacyBadge

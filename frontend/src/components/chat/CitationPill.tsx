'use client'

/**
 * CitationPill.tsx — Inline citation badge rendered inside AI message text.
 *
 * Supported citation kinds:
 *   mcp     — [mcp:N]       — MCP tool-call reference (1-based per turn)
 *   source  — [source:ID]   — SurrealDB source record
 *   note    — [note:ID]     — SurrealDB note record
 *   insight — [insight:ID]  — SurrealDB insight record
 *
 * v0.8.0 Phase 4 Task 14
 *
 * MCP popover (v0.8.1 Item 3):
 *   The parent message renderer passes `messageId` as a prop. The MCP
 *   popover looks up tool-call payloads from the TanStack Query cache
 *   keyed by ['mcp', 'tool-calls', messageId]. Payloads are stashed
 *   there by useNotebookChat when the /chat/stream mcp_tool_calls
 *   NDJSON event arrives. Falls back to a placeholder for old sessions
 *   that predate this feature.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { FileText, Lightbulb, StickyNote, Wrench } from 'lucide-react'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { useQueryClient } from '@tanstack/react-query'
import { useSource } from '@/lib/hooks/use-sources'
import { useNote } from '@/lib/hooks/use-notes'
import { useInsight } from '@/lib/hooks/use-insights'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { CitationKind } from '@/lib/utils/citations'
import type { McpToolCall } from '@/lib/types/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CitationPillProps {
  /** Citation kind: mcp | source | note | insight */
  kind: CitationKind
  /** The raw reference value — integer string for mcp, record ID for others */
  value: string
  /**
   * v0.8.1 Item 3 — ID of the AI message this pill belongs to.
   * Used by McpPopoverContent to look up tool-call payloads from the
   * TanStack Query cache. Optional for backward compatibility (pills
   * rendered without messageId fall back to the placeholder).
   */
  messageId?: string
}

// ---------------------------------------------------------------------------
// Sub-components: popover body per kind
// ---------------------------------------------------------------------------

/** Popover body for [source:ID] pills */
function SourcePopoverContent({ id }: { id: string }) {
  const { t } = useTranslation()
  const { data, isLoading } = useSource(id)

  if (isLoading) {
    return <p className="text-xs text-muted-foreground">{t('common.loading')}</p>
  }

  return (
    <div className="space-y-1">
      <p className="text-xs font-semibold text-foreground">
        {t('chat.citations.sourceLabel')}
      </p>
      {data?.title ? (
        <p className="text-xs text-muted-foreground">{data.title}</p>
      ) : (
        <p className="text-xs text-muted-foreground italic">
          {t('sources.untitledSource')}
        </p>
      )}
      {data?.full_text && (
        <p className="text-xs text-muted-foreground line-clamp-3 mt-1">
          {data.full_text.slice(0, 200)}
        </p>
      )}
    </div>
  )
}

/** Popover body for [note:ID] pills */
function NotePopoverContent({ id }: { id: string }) {
  const { t } = useTranslation()
  const { data, isLoading } = useNote(id)

  if (isLoading) {
    return <p className="text-xs text-muted-foreground">{t('common.loading')}</p>
  }

  return (
    <div className="space-y-1">
      <p className="text-xs font-semibold text-foreground">
        {t('chat.citations.noteLabel')}
      </p>
      {data?.title ? (
        <p className="text-xs text-muted-foreground">{data.title}</p>
      ) : (
        <p className="text-xs text-muted-foreground italic">
          {t('sources.untitledNote')}
        </p>
      )}
      {data?.content && (
        <p className="text-xs text-muted-foreground line-clamp-3 mt-1">
          {data.content.slice(0, 200)}
        </p>
      )}
    </div>
  )
}

/** Popover body for [insight:ID] pills */
function InsightPopoverContent({ id }: { id: string }) {
  const { t } = useTranslation()
  // v0.8.1 Item 4 — switched from useSource(id) to useInsight(id). The MVP
  // wrongly assumed insight IDs were sourceish records; in practice the LLM
  // emits source_insight:xxx record IDs (per CITING INSTRUCTIONS in
  // prompts/chat/system.jinja:51-52), so the source GET would 404 silently
  // and the popover always showed the italic "common.insight" fallback.
  const { data, isLoading } = useInsight(id)

  if (isLoading) {
    return <p className="text-xs text-muted-foreground">{t('common.loading')}</p>
  }

  // v0.8.1 Item 4 follow-up — SourceInsightResponse has no `title` field
  // (shape: id, source_id, insight_type, content, created, updated). Show
  // the insight_type as the heading and a truncated content excerpt as
  // the body, matching how Source and Note popovers display their data.
  return (
    <div className="space-y-1">
      <p className="text-xs font-semibold text-foreground">
        {t('chat.citations.insightLabel')}
      </p>
      {data?.insight_type ? (
        <p className="text-xs text-muted-foreground capitalize">
          {data.insight_type.replace(/_/g, ' ')}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground italic">
          {t('common.insight')}
        </p>
      )}
      {data?.content && (
        <p className="text-xs text-muted-foreground line-clamp-3 mt-1">
          {data.content.slice(0, 200)}
        </p>
      )}
    </div>
  )
}

/** Popover body for [mcp:N] pills.
 *  v0.8.1 Item 3: reads MCP tool-call payload from TanStack Query cache
 *  (keyed by messageId, stashed by useNotebookChat on mcp_tool_calls event).
 *  Falls back to updated placeholder for old sessions with no cached data.
 */
function McpPopoverContent({ index, messageId }: { index: string; messageId?: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  // Read-only cache lookup — no fetcher, so this never triggers a network
  // request. Returns undefined if the cache key was never populated.
  const calls = messageId
    ? (queryClient.getQueryData<McpToolCall[]>(['mcp', 'tool-calls', messageId]) ?? null)
    : null

  // Find the specific call matching this pill's 1-based index.
  const callIndex = parseInt(index, 10)
  const call = calls?.find(c => c.index === callIndex) ?? null

  if (!call) {
    // Fallback — either messageId not provided (old code path) or the
    // cache entry was never populated (old session pre-v0.8.1 or MCP
    // was not enabled during this turn).
    return (
      <div className="space-y-1">
        <p className="text-xs font-semibold text-foreground">
          {t('chat.citations.toolCallLabel')}
        </p>
        <p className="text-xs text-muted-foreground">
          {t('chat.citations.mcpIndexLabel').replace('{index}', index)}
        </p>
        <p className="text-xs text-muted-foreground italic mt-1">
          {t('chat.citations.mcpPlaceholder')}
        </p>
      </div>
    )
  }

  // Payload found — render tool name, compact args JSON, and truncated result.
  const argsJson = JSON.stringify(call.args, null, 2)
  const resultExcerpt = call.text.slice(0, 500)

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-foreground">
        {t('chat.citations.toolCallLabel')}
      </p>
      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">
          {t('chat.citations.mcpToolName')}: <span className="font-mono text-foreground">{call.name}</span>
        </p>
      </div>
      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">{t('chat.citations.mcpArgs')}</p>
        <pre className="text-[0.65rem] bg-muted rounded p-1 overflow-x-auto max-w-full whitespace-pre-wrap break-all">
          {argsJson}
        </pre>
      </div>
      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">{t('chat.citations.mcpResult')}</p>
        <p className="text-xs text-muted-foreground line-clamp-6 break-words">
          {resultExcerpt}
          {call.text.length > 500 && '…'}
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Kind → badge style mapping
// ---------------------------------------------------------------------------

const BADGE_STYLES: Record<CitationKind, string> = {
  mcp: 'bg-violet-100 text-violet-700 border-violet-200 hover:bg-violet-200 dark:bg-violet-900/30 dark:text-violet-300 dark:border-violet-700 dark:hover:bg-violet-900/50',
  source: 'bg-blue-100 text-blue-700 border-blue-200 hover:bg-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-700 dark:hover:bg-blue-900/50',
  note: 'bg-amber-100 text-amber-700 border-amber-200 hover:bg-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-700 dark:hover:bg-amber-900/50',
  insight: 'bg-emerald-100 text-emerald-700 border-emerald-200 hover:bg-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-700 dark:hover:bg-emerald-900/50',
}

const KIND_ICONS: Record<CitationKind, React.ElementType> = {
  mcp: Wrench,
  source: FileText,
  note: StickyNote,
  insight: Lightbulb,
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * CitationPill renders a small inline badge for a single citation marker.
 * Click or press Enter/Space to open a popover with more detail.
 *
 * Accessibility: the trigger is a focusable button; Radix Popover handles
 * keyboard navigation (Enter/Space to open, Escape to close, focus-trap).
 */
export function CitationPill({ kind, value, messageId }: CitationPillProps) {
  const { t } = useTranslation()
  const Icon = KIND_ICONS[kind]

  // v0.8.76 — citation hover-preview (improvement roadmap, Batch 1). The
  // Popover already shows the cited document's title + snippet on click; this
  // makes it ALSO open on hover (and keyboard focus) so users can skim the
  // grounding without leaving the answer. We control the Popover's open state
  // with small open/close delays and a grace window, so moving the cursor from
  // the pill into the popover doesn't close it. Click still toggles via Radix's
  // own onOpenChange — so if the hover timing ever misbehaves, click-to-open
  // keeps working exactly as before.
  const [open, setOpen] = useState(false)
  const openTimer = useRef<number | null>(null)
  const closeTimer = useRef<number | null>(null)

  const clearTimers = useCallback(() => {
    if (openTimer.current) { window.clearTimeout(openTimer.current); openTimer.current = null }
    if (closeTimer.current) { window.clearTimeout(closeTimer.current); closeTimer.current = null }
  }, [])
  const cancelClose = useCallback(() => {
    if (closeTimer.current) { window.clearTimeout(closeTimer.current); closeTimer.current = null }
  }, [])
  const hoverOpen = useCallback(() => {
    cancelClose()
    if (open || openTimer.current) return
    openTimer.current = window.setTimeout(() => setOpen(true), 280)
  }, [open, cancelClose])
  const hoverClose = useCallback(() => {
    if (openTimer.current) { window.clearTimeout(openTimer.current); openTimer.current = null }
    closeTimer.current = window.setTimeout(() => setOpen(false), 140)
  }, [])
  useEffect(() => () => clearTimers(), [clearTimers])

  // Visible badge label
  const label =
    kind === 'mcp'
      ? `[${value}]`
      : `${kind.slice(0, 2)}:${value.slice(0, 8)}`

  // Accessible aria-label
  const ariaLabel =
    kind === 'mcp'
      ? t('chat.citations.toolCallLabel') + ' ' + value
      : `${kind} ${value}`

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={ariaLabel}
          className={[
            'inline-flex items-center gap-0.5',
            'mx-0.5 px-1.5 py-0 rounded-full border text-[0.65rem] font-semibold',
            'cursor-pointer transition-colors',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
            // Prevent citation click from navigating or propagating to parent anchor elements
            'relative z-10',
            BADGE_STYLES[kind],
          ].join(' ')}
          onMouseEnter={hoverOpen}
          onMouseLeave={hoverClose}
          onFocus={() => { clearTimers(); setOpen(true) }}
          onBlur={hoverClose}
          // Prevent any parent link from intercepting the click; Radix's own
          // controlled onOpenChange still toggles the popover on click.
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
          }}
        >
          <Icon className="h-2.5 w-2.5" aria-hidden="true" />
          <span>{label}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="w-72 text-sm"
        side="top"
        align="center"
        onMouseEnter={cancelClose}
        onMouseLeave={hoverClose}
        // Don't steal focus when opened by hover (jarring mid-read); Escape and
        // outside-click still close via Radix, keyboard users can Tab in.
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        {kind === 'mcp' && <McpPopoverContent index={value} messageId={messageId} />}
        {kind === 'source' && <SourcePopoverContent id={value} />}
        {kind === 'note' && <NotePopoverContent id={value} />}
        {kind === 'insight' && <InsightPopoverContent id={value} />}
      </PopoverContent>
    </Popover>
  )
}

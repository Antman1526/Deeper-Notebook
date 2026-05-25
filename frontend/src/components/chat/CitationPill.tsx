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
 * MCP popover:
 *   Currently shows a placeholder because the backend chat stream does not yet
 *   include the tool-call payload alongside the token stream.
 *   TODO(v0.8.1): extend the SSE wire format to include a sentinel event
 *   {"type":"mcp_call_result","index":N,"name":"...","args":{...},"text":"..."}
 *   and collect these in a side-buffer here so the popover can show the
 *   actual search query / result text.
 */

import React from 'react'
import { FileText, Lightbulb, StickyNote, Wrench } from 'lucide-react'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { useSource } from '@/lib/hooks/use-sources'
import { useNote } from '@/lib/hooks/use-notes'
import { useInsight } from '@/lib/hooks/use-insights'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { CitationKind } from '@/lib/utils/citations'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CitationPillProps {
  /** Citation kind: mcp | source | note | insight */
  kind: CitationKind
  /** The raw reference value — integer string for mcp, record ID for others */
  value: string
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

  return (
    <div className="space-y-1">
      <p className="text-xs font-semibold text-foreground">
        {t('chat.citations.insightLabel')}
      </p>
      {data?.title ? (
        <p className="text-xs text-muted-foreground">{data.title}</p>
      ) : (
        <p className="text-xs text-muted-foreground italic">
          {t('common.insight')}
        </p>
      )}
    </div>
  )
}

/** Popover body for [mcp:N] pills.
 *  Option A (MVP): shows marker + placeholder until v0.8.1 stream contract change.
 */
function McpPopoverContent({ index }: { index: string }) {
  const { t } = useTranslation()
  return (
    <div className="space-y-1">
      <p className="text-xs font-semibold text-foreground">
        {t('chat.citations.toolCallLabel')}
      </p>
      <p className="text-xs text-muted-foreground">
        {t('chat.citations.mcpIndexLabel').replace('{index}', index)}
      </p>
      <p className="text-xs text-muted-foreground italic mt-1">
        {/* v0.8.1 TODO: replace this placeholder once the SSE stream emits
            {"type":"mcp_call_result","index":N,"name":"...","args":{...},"text":"..."}
            so we can display the actual search query and result snippet. */}
        {t('chat.citations.mcpPlaceholder')}
      </p>
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
export function CitationPill({ kind, value }: CitationPillProps) {
  const { t } = useTranslation()
  const Icon = KIND_ICONS[kind]

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
    <Popover>
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
          // Prevent any parent link from intercepting the click
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
          }}
        >
          <Icon className="h-2.5 w-2.5" aria-hidden="true" />
          <span>{label}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-72 text-sm" side="top" align="center">
        {kind === 'mcp' && <McpPopoverContent index={value} />}
        {kind === 'source' && <SourcePopoverContent id={value} />}
        {kind === 'note' && <NotePopoverContent id={value} />}
        {kind === 'insight' && <InsightPopoverContent id={value} />}
      </PopoverContent>
    </Popover>
  )
}

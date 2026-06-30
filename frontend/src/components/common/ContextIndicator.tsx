'use client'

import { FileText, Lightbulb, StickyNote } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

interface ContextIndicatorProps {
  sourcesInsights: number
  sourcesFull: number
  notesCount: number
  tokenCount?: number
  charCount?: number
  // v0.8.89 — when provided, show a "Using X of Y sources" summary with a
  // popover listing the in-context source names (per-source-filtering
  // transparency). Omitted by callers that don't have the totals (e.g. the
  // source-chat panel), which keep the legacy badges-only display.
  totalSources?: number
  contextSourceTitles?: string[]
  className?: string
}

// Helper function to format large numbers with K/M suffixes
function formatNumber(num: number): string {
  if (num >= 1000000) {
    return `${(num / 1000000).toFixed(1)}M`
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(1)}K`
  }
  return num.toString()
}

export function ContextIndicator({
  sourcesInsights,
  sourcesFull,
  notesCount,
  tokenCount,
  charCount,
  totalSources,
  contextSourceTitles,
  className
}: ContextIndicatorProps) {
  const hasContext = (sourcesInsights + sourcesFull) > 0 || notesCount > 0
  // v0.8.89 — when we know the total, always render the "Using X of Y" summary
  // (even at 0) so the filtering is discoverable. Legacy callers (no total)
  // keep the prior "nothing in context" hint.
  const showSummary = totalSources !== undefined
  const inContextSources = sourcesInsights + sourcesFull

  if (!hasContext && !showSummary) {
    return (
      <div className={cn('flex-shrink-0 text-xs text-muted-foreground py-2 px-3 border-t', className)}>
        No sources or notes included in context. Toggle icons on cards to include them.
      </div>
    )
  }

  return (
    <div className={cn('flex-shrink-0 flex items-center justify-between gap-2 py-2 px-3 border-t bg-muted/30', className)}>
      <div className="flex items-center gap-2">
        {showSummary ? (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="text-xs font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                Using {inContextSources} of {totalSources} source{totalSources === 1 ? '' : 's'}
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="max-h-64 w-72 overflow-y-auto">
              {contextSourceTitles && contextSourceTitles.length > 0 ? (
                <ul className="space-y-1 text-xs">
                  {contextSourceTitles.map((name, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
                      <span className="truncate">{name}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">
                  No sources in context. Toggle a source’s icon in the Sources panel to include it.
                </p>
              )}
            </PopoverContent>
          </Popover>
        ) : (
          <span className="text-xs font-medium text-muted-foreground">Context:</span>
        )}

        <div className="flex items-center gap-1.5">
          {sourcesInsights > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant="outline" className="text-xs flex items-center gap-1 px-1.5 py-0.5 text-amber-600 border-amber-600/50 cursor-default">
                  <Lightbulb className="h-3 w-3" />
                  <span>{sourcesInsights}</span>
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                <p>Insights for {sourcesInsights} source{sourcesInsights !== 1 ? 's' : ''}</p>
              </TooltipContent>
            </Tooltip>
          )}

          {sourcesFull > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant="outline" className="text-xs flex items-center gap-1 px-1.5 py-0.5 text-primary border-primary/50 cursor-default">
                  <FileText className="h-3 w-3" />
                  <span>{sourcesFull}</span>
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                <p>{sourcesFull} full source{sourcesFull !== 1 ? 's' : ''}</p>
              </TooltipContent>
            </Tooltip>
          )}
        </div>

        {notesCount > 0 && (
          <>
            {(sourcesInsights > 0 || sourcesFull > 0) && (
              <span className="text-muted-foreground">•</span>
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant="outline" className="text-xs flex items-center gap-1 px-1.5 py-0.5 text-primary border-primary/50 cursor-default">
                  <StickyNote className="h-3 w-3" />
                  <span>{notesCount}</span>
                </Badge>
              </TooltipTrigger>
              <TooltipContent>
                <p>{notesCount} full note{notesCount !== 1 ? 's' : ''}</p>
              </TooltipContent>
            </Tooltip>
          </>
        )}
      </div>

      {(tokenCount !== undefined || charCount !== undefined) && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {tokenCount !== undefined && tokenCount > 0 && (
            <span>{formatNumber(tokenCount)} tokens</span>
          )}
          {tokenCount !== undefined && charCount !== undefined && tokenCount > 0 && charCount > 0 && (
            <span>/</span>
          )}
          {charCount !== undefined && charCount > 0 && (
            <span>{formatNumber(charCount)} chars</span>
          )}
        </div>
      )}
    </div>
  )
}

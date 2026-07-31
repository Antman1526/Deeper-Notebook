import { useMemo } from 'react'

import {
  documentMetrics,
  type DocumentMetrics,
} from '@/lib/knowledge/document-metrics'

export interface DocumentMetricsFormatters {
  words: (count: number) => string
  characters: (count: number) => string
  readingMinutes: (count: number) => string
  selectionMetrics: (
    metrics: Pick<DocumentMetrics, 'words' | 'characters'>,
  ) => string
}

interface DocumentMetricsFooterProps {
  text: string
  selectionText: string
  visible: boolean
  hasDocument: boolean
  formatters: DocumentMetricsFormatters
  emptyLabel: string
}

export function DocumentMetricsFooter({
  text,
  selectionText,
  visible,
  hasDocument,
  formatters,
  emptyLabel,
}: DocumentMetricsFooterProps) {
  const metrics = useMemo(() => documentMetrics(text), [text])
  const selectionMetrics = useMemo(
    () => documentMetrics(selectionText),
    [selectionText],
  )
  const documentSummary = useMemo(() => [
    formatters.words(metrics.words),
    formatters.characters(metrics.characters),
    formatters.readingMinutes(metrics.readingMinutes),
  ].join(', '), [formatters, metrics])

  if (!visible) return null

  return (
    <footer
      role="status"
      aria-live="polite"
      aria-label={hasDocument ? documentSummary : emptyLabel}
      tabIndex={0}
      className="mt-3 flex h-10 shrink-0 items-center gap-x-4 overflow-x-auto border-t px-1 text-xs text-muted-foreground"
    >
      {hasDocument ? (
        <div className="flex shrink-0 items-center gap-x-3">
          <span>{formatters.words(metrics.words)}</span>
          <span>{formatters.characters(metrics.characters)}</span>
          <span>{formatters.readingMinutes(metrics.readingMinutes)}</span>
        </div>
      ) : (
        <span>{emptyLabel}</span>
      )}
      {hasDocument && selectionText && (
        <div
          data-selection-metrics
          className="flex shrink-0 items-center gap-x-3 border-l pl-4"
        >
          <span className="font-medium text-foreground">
            {formatters.selectionMetrics(selectionMetrics)}
          </span>
        </div>
      )}
    </footer>
  )
}

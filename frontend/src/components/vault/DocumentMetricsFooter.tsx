import { documentMetrics } from '@/lib/knowledge/document-metrics'

export interface DocumentMetricsLabels {
  words: string
  characters: string
  charactersWithoutWhitespace: string
  readingMinutes: string
  selection: string
}

interface DocumentMetricsFooterProps {
  text: string
  selectionText: string
  visible: boolean
  labels: DocumentMetricsLabels
}

function Metrics({
  text,
  labels,
}: Pick<DocumentMetricsFooterProps, 'text' | 'labels'>) {
  const metrics = documentMetrics(text)

  return (
    <>
      <span>{labels.words}: {metrics.words}</span>
      <span>{labels.characters}: {metrics.characters}</span>
      <span>
        {labels.charactersWithoutWhitespace}: {metrics.charactersWithoutWhitespace}
      </span>
      <span>{labels.readingMinutes}: {metrics.readingMinutes}</span>
    </>
  )
}

export function DocumentMetricsFooter({
  text,
  selectionText,
  visible,
  labels,
}: DocumentMetricsFooterProps) {
  if (!visible) return null

  return (
    <footer
      role="status"
      aria-live="polite"
      className="mt-3 flex h-10 shrink-0 items-center gap-x-4 overflow-x-auto border-t px-1 text-xs text-muted-foreground"
    >
      <div className="flex shrink-0 items-center gap-x-3">
        <Metrics text={text} labels={labels} />
      </div>
      {selectionText && (
        <div
          data-selection-metrics
          className="flex shrink-0 items-center gap-x-3 border-l pl-4"
        >
          <span className="font-medium text-foreground">{labels.selection}</span>
          <Metrics text={selectionText} labels={labels} />
        </div>
      )}
    </footer>
  )
}

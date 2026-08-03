'use client'

import type { PodcastSelection } from '@/lib/podcasts/selection'
import type { PodcastSelectionPreview, PodcastSelectionPreviewEntry, PodcastSelectionState } from '@/lib/types/podcasts'

export interface ResearchSetPanelProps {
  selections: PodcastSelection[]
  preview?: PodcastSelectionPreview | null
  onPrepare?: () => void
  isPreparing?: boolean
}

const PROBLEM_STATES: PodcastSelectionState[] = ['unavailable', 'changed', 'empty', 'failed_parse']
const STATE_LABELS: Record<PodcastSelectionState, string> = {
  included: 'Included',
  duplicate: 'Duplicate',
  unavailable: 'Unavailable',
  changed: 'Changed since preview',
  empty: 'Empty',
  failed_parse: 'Failed to parse',
  oversize: 'Oversize',
}

function entriesFor(preview: PodcastSelectionPreview | null | undefined): PodcastSelectionPreviewEntry[] {
  return preview?.entries ?? []
}

function safeTitle(value: string): string {
  if (/^(?:[\\/]|[A-Za-z]:[\\/])/.test(value)) return value.split(/[\\/]/).pop() || 'Untitled reference'
  return value
}

function safeReason(value: string): string {
  return value.replace(/(?:[\\/][^\s,;]+)+/g, '[path redacted]')
}

function EntryList({ entries, label }: { entries: PodcastSelectionPreviewEntry[]; label: string }) {
  if (entries.length === 0) return null
  return (
    <section aria-label={label} className="space-y-2">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</h4>
      <ul className="space-y-1 text-sm">
        {entries.map((entry) => (
          <li key={`${entry.stableId}:${entry.revisionId ?? 'current'}:${entry.state}`} className="flex items-start justify-between gap-3 rounded border px-3 py-2">
            <span className="min-w-0 truncate" title={safeTitle(entry.title)}>{safeTitle(entry.title)}</span>
            <span className="shrink-0 text-xs text-muted-foreground">{STATE_LABELS[entry.state]}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ResearchSetPanel({ selections, preview, onPrepare, isPreparing = false }: ResearchSetPanelProps) {
  const entries = entriesFor(preview)
  const included = entries.filter((entry) => entry.state === 'included')
  const duplicates = entries.filter((entry) => entry.state === 'duplicate')
  const oversize = entries.filter((entry) => entry.state === 'oversize')
  const problems = entries.filter((entry) => PROBLEM_STATES.includes(entry.state))
  const hasEmptySelection = selections.length === 0 || (preview != null && entries.length === 0)

  return (
    <section data-studio-region="research-set" data-region="research-set" aria-label="Research Set" className="space-y-3 rounded-md border p-4">
      <header>
        <h3 className="font-semibold">Research Set</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {preview ? `${included.length} included · ${problems.length + duplicates.length + oversize.length} excluded/problem` : `${selections.length} selected reference${selections.length === 1 ? '' : 's'}`}
        </p>
      </header>

      {!preview && onPrepare ? (
        <button type="button" className="rounded-md border px-3 py-2 text-sm" onClick={onPrepare} disabled={isPreparing || selections.length === 0}>
          {isPreparing ? 'Preparing research set…' : 'Prepare research set'}
        </button>
      ) : null}

      {hasEmptySelection ? (
        <p className="rounded border border-dashed p-3 text-sm text-muted-foreground">No readable references selected</p>
      ) : null}

      <div className="space-y-3">
        <EntryList entries={included} label="Included" />
        <EntryList entries={problems} label="Problems" />
        <EntryList entries={duplicates} label="Duplicates" />
        <EntryList entries={oversize} label="Oversize" />
      </div>

      {preview ? (
        <div className="space-y-1 text-xs text-muted-foreground" aria-live="polite">
          <p>{preview.includedCharacters.toLocaleString()} characters included in the current worker.</p>
          {preview.requiresBatchEngine ? <p>Selection requires a batch engine; the current worker will not truncate it.</p> : null}
          {!preview.currentWorkerEligible && !preview.requiresBatchEngine ? <p>Selection is not eligible until the listed problems are resolved.</p> : null}
          {preview.blockedReasons.length > 0 ? <p>{preview.blockedReasons.map(safeReason).join(', ')}</p> : null}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">References are resolved server-side; absolute source paths are never displayed.</p>
      )}
    </section>
  )
}

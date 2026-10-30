'use client'

import { useTranslation } from '@/lib/hooks/use-translation'
import { formatNumber } from '@/lib/utils/format'
import type { PodcastSelection } from '@/lib/podcasts/selection'
import type { PodcastSelectionPreview, PodcastSelectionPreviewEntry, PodcastSelectionState } from '@/lib/types/podcasts'
import { isAbsoluteFilesystemPath, redactAbsolutePaths } from '@/lib/podcasts/safe-text'

export interface ResearchSetPanelProps {
  selections: PodcastSelection[]
  preview?: PodcastSelectionPreview | null
  onPrepare?: () => void
  isPreparing?: boolean
}

const PROBLEM_STATES: PodcastSelectionState[] = ['unavailable', 'changed', 'empty', 'failed_parse']
const STATE_LABEL_KEYS: Record<PodcastSelectionState, string> = {
  included: 'podcasts.researchSetPanel.stateIncluded',
  duplicate: 'podcasts.researchSetPanel.stateDuplicate',
  unavailable: 'podcasts.researchSetPanel.stateUnavailable',
  changed: 'podcasts.researchSetPanel.stateChanged',
  empty: 'podcasts.researchSetPanel.stateEmpty',
  failed_parse: 'podcasts.researchSetPanel.stateFailedParse',
  oversize: 'podcasts.researchSetPanel.stateOversize',
}

function entriesFor(preview: PodcastSelectionPreview | null | undefined): PodcastSelectionPreviewEntry[] {
  return preview?.entries ?? []
}

function safeTitle(value: string, untitledLabel: string): string {
  if (isAbsoluteFilesystemPath(value)) return value.split(/[\\/]/).filter(Boolean).pop() || untitledLabel
  return redactAbsolutePaths(value)
}

function safeReason(value: string): string {
  return redactAbsolutePaths(value)
}

function EntryList({ entries, label }: { entries: PodcastSelectionPreviewEntry[]; label: string }) {
  const { t } = useTranslation()
  if (entries.length === 0) return null
  const untitledLabel = t('podcasts.researchSetPanel.untitledReference')
  return (
    <section aria-label={label} className="space-y-2">
      <h4 className="text-xs font-semibold text-muted-foreground">{label}</h4>
      <ul className="space-y-1 text-sm">
        {entries.map((entry) => (
          <li key={`${entry.stableId}:${entry.revisionId ?? 'current'}:${entry.state}`} className="flex items-start justify-between gap-3 rounded border px-3 py-2">
            <div className="min-w-0">
              <span className="block truncate" title={safeTitle(entry.title, untitledLabel)}>{safeTitle(entry.title, untitledLabel)}</span>
              <span className="block truncate text-xs text-muted-foreground" title={safeReason(entry.reason)}>{safeReason(entry.reason)}</span>
            </div>
            <span className="shrink-0 text-xs text-muted-foreground">{t(STATE_LABEL_KEYS[entry.state])}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ResearchSetPanel({ selections, preview, onPrepare, isPreparing = false }: ResearchSetPanelProps) {
  const { t, language } = useTranslation()
  const entries = entriesFor(preview)
  const included = entries.filter((entry) => entry.state === 'included')
  const duplicates = entries.filter((entry) => entry.state === 'duplicate')
  const oversize = entries.filter((entry) => entry.state === 'oversize')
  const problems = entries.filter((entry) => PROBLEM_STATES.includes(entry.state))
  const hasEmptySelection = selections.length === 0 || (preview != null && entries.length === 0)

  return (
    <section data-studio-region="research-set" data-region="research-set" aria-label={t('podcasts.researchSetPanel.title')} className="space-y-3 rounded-md border p-4">
      <header>
        <h3 className="font-semibold">{t('podcasts.researchSetPanel.title')}</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {preview ? t('podcasts.researchSetPanel.previewSummary', { included: included.length, excluded: problems.length + duplicates.length + oversize.length }) : selections.length === 1 ? t('podcasts.researchSetPanel.selectedReferencesOne', { count: selections.length }) : t('podcasts.researchSetPanel.selectedReferencesOther', { count: selections.length })}
        </p>
      </header>

      {!preview && onPrepare ? (
        <button type="button" className="rounded-md border px-3 py-2 text-sm" onClick={onPrepare} disabled={isPreparing || selections.length === 0}>
          {isPreparing ? t('podcasts.researchSetPanel.preparing') : t('podcasts.researchSetPanel.prepare')}
        </button>
      ) : null}

      {hasEmptySelection ? (
        <p className="rounded border border-dashed p-3 text-sm text-muted-foreground">{t('podcasts.researchSetPanel.noReadableReferences')}</p>
      ) : null}

      <div className="space-y-3">
        <EntryList entries={included} label={t('podcasts.researchSetPanel.included')} />
        <EntryList entries={problems} label={t('podcasts.researchSetPanel.problems')} />
        <EntryList entries={duplicates} label={t('podcasts.researchSetPanel.duplicates')} />
        <EntryList entries={oversize} label={t('podcasts.researchSetPanel.oversize')} />
      </div>

      {preview ? (
        <div className="space-y-1 text-xs text-muted-foreground" aria-live="polite">
          <p>{t('podcasts.researchSetPanel.charactersIncluded', { characters: formatNumber(preview.includedCharacters, language) })}</p>
          {preview.requiresBatchEngine ? <p>{t('podcasts.researchSetPanel.requiresBatchEngine')}</p> : null}
          {!preview.currentWorkerEligible && !preview.requiresBatchEngine ? <p>{t('podcasts.researchSetPanel.notEligible')}</p> : null}
          {preview.blockedReasons.length > 0 ? <p>{preview.blockedReasons.map(safeReason).join(', ')}</p> : null}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">{t('podcasts.researchSetPanel.referencesNotice')}</p>
      )}
    </section>
  )
}

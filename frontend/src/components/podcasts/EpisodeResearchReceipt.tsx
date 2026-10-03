import { useTranslation } from '@/lib/hooks/use-translation'

type SelectionSummary = {
  version?: number
  total_count?: number
  included_count?: number
  authority_counts?: Record<string, number>
}

type EditorialBrief = {
  central_question?: string | null
  audience?: string | null
  outline?: string[]
}

type ModelPlanReceipt = {
  version?: number
  role?: string
  outcome?: string
  reason?: string
}

export function EpisodeResearchReceipt({
  selectionSummary,
  selectionFingerprint,
  editorialBrief,
  modelPlanReceipts,
}: {
  selectionSummary?: SelectionSummary | null
  selectionFingerprint?: string | null
  editorialBrief?: EditorialBrief | null
  modelPlanReceipts?: ModelPlanReceipt[]
}) {
  const { t } = useTranslation()
  const included = selectionSummary?.included_count ?? 0
  const total = selectionSummary?.total_count ?? 0
  const externalReadOnly = selectionSummary?.authority_counts?.external_read_only ?? 0
  const appOwned = selectionSummary?.authority_counts?.app_owned ?? 0
  const routeCount = modelPlanReceipts?.length ?? 0
  const fingerprint = selectionFingerprint
    ? `${selectionFingerprint.slice(0, 12)}…${selectionFingerprint.slice(-8)}`
    : null

  if (!selectionSummary && !selectionFingerprint && !editorialBrief && routeCount === 0) {
    return null
  }

  return (
    <section aria-label={t('podcasts.episodeResearchReceipt.title')} className="space-y-3 rounded-md border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-foreground">{t('podcasts.episodeResearchReceipt.title')}</h4>
        {/* v0.8.130 — was "Phase 2 provenance": an internal roadmap label is not user-facing copy. */}
        <span className="text-xs text-muted-foreground">{t('podcasts.episodeResearchReceipt.provenance')}</span>
      </div>
      {selectionSummary ? (
        <div className="space-y-1 text-xs text-muted-foreground">
          <p>{t('podcasts.episodeResearchReceipt.sourcesIncluded', { included, total })}</p>
          <p>{appOwned > 0 ? t('podcasts.episodeResearchReceipt.externalReadOnlyWithAppOwned', { external: externalReadOnly, appOwned }) : t('podcasts.episodeResearchReceipt.externalReadOnly', { external: externalReadOnly })}</p>
        </div>
      ) : null}
      {fingerprint ? <p className="font-mono text-xs text-muted-foreground">{t('podcasts.episodeResearchReceipt.selection', { fingerprint })}</p> : null}
      {routeCount > 0 ? <p className="text-xs text-muted-foreground">{routeCount === 1 ? t('podcasts.episodeResearchReceipt.routesRecordedOne', { count: routeCount }) : t('podcasts.episodeResearchReceipt.routesRecordedOther', { count: routeCount })}</p> : null}
      {editorialBrief ? (
        <div className="space-y-1 text-xs text-muted-foreground">
          {editorialBrief.central_question ? <p>{editorialBrief.central_question}</p> : null}
          {editorialBrief.audience ? <p>{editorialBrief.audience}</p> : null}
          {editorialBrief.outline?.length ? <p>{editorialBrief.outline.join(' · ')}</p> : null}
        </div>
      ) : null}
    </section>
  )
}

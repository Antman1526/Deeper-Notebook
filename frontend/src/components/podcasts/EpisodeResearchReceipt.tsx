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
    <section aria-label="Research receipt" className="space-y-3 rounded-md border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-foreground">Research receipt</h4>
        <span className="text-xs text-muted-foreground">Phase 2 provenance</span>
      </div>
      {selectionSummary ? (
        <div className="space-y-1 text-xs text-muted-foreground">
          <p>{included} of {total} sources included</p>
          <p>{externalReadOnly} external read-only{appOwned > 0 ? ` · ${appOwned} app-owned` : ''}</p>
        </div>
      ) : null}
      {fingerprint ? <p className="font-mono text-xs text-muted-foreground">Selection {fingerprint}</p> : null}
      {routeCount > 0 ? <p className="text-xs text-muted-foreground">{routeCount} local route{routeCount === 1 ? '' : 's'} recorded</p> : null}
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

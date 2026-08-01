'use client'

export interface ResearchCoreReadiness {
  state: 'ready' | 'loading' | 'unavailable'
  detail: string
  models?: Array<{ id: string; provider: string; path?: string }>
}

interface ResearchCoreHeaderProps {
  workspaceTitle: string
  authoritySummary: { appOwned: number; externalReadOnly: number }
  saveState: string
  readiness: ResearchCoreReadiness
  memoryPressure: { state: 'normal' | 'elevated' | 'high'; detail: string }
  queuedWorkCount: number
}

function redactModelPaths(value: string): string {
  return value
    .replace(/(^|\s)\/(?:[^\n]*)/g, '$1[local path redacted]')
    .replace(/(^|\s)[A-Za-z]:\\(?:[^\n]*)/g, '$1[local path redacted]')
}

export function ResearchCoreHeader({
  workspaceTitle,
  authoritySummary,
  saveState,
  readiness,
  memoryPressure,
  queuedWorkCount,
}: ResearchCoreHeaderProps) {
  const readinessDetail = redactModelPaths(readiness.detail)
  const readinessLabel = {
    ready: 'Local readiness: ready',
    loading: 'Local readiness: loading',
    unavailable: 'Local readiness: unavailable',
  }[readiness.state]
  return (
    <header aria-label="Research Core workspace" className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b px-4 py-3">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-semibold">{workspaceTitle}</h1>
        <p className="text-sm text-muted-foreground">
          {authoritySummary.appOwned} app-owned · {authoritySummary.externalReadOnly} external read-only
        </p>
      </div>
      <dl className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <div><dt className="sr-only">Save state</dt><dd>{saveState}</dd></div>
        <div><dt className="sr-only">Memory pressure</dt><dd data-state={memoryPressure.state}>{memoryPressure.detail}</dd></div>
        <div><dt className="sr-only">Queued work</dt><dd>{queuedWorkCount} queued</dd></div>
      </dl>
      <details className="basis-full text-sm">
        <summary>{readinessLabel} — {readinessDetail}</summary>
        {readiness.models?.length ? (
          <ul className="mt-2 flex flex-wrap gap-x-3 text-muted-foreground" aria-label="Local readiness details">
            {readiness.models.map((model) => (
              <li key={`${model.provider}:${model.id}`}>{model.id} · {model.provider}</li>
            ))}
          </ul>
        ) : null}
      </details>
    </header>
  )
}

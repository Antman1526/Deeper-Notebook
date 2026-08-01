'use client'

interface PodcastStudioProps {
  seedDocumentIds: string[]
  modelPlans?: Array<{
    label: string
    plan: { outcome: 'ready' | 'blocked' | 'approval_required'; reason: string } | undefined
  }>
}

const timeline = [
  ['Research Set Preview', 'Current selection'],
  ['Editorial Brief', 'Configure before production'],
  ['Outline Storyboard', 'Current review gate'],
  ['Script/Voice Job', 'Begins after outline approval'],
  ['Episode', 'Current production output'],
] as const

/**
 * Shared Phase-2 controller shell. It presents only current, reviewable
 * production stages and makes the later evidence engine boundary explicit.
 */
export function PodcastStudio({ seedDocumentIds, modelPlans = [] }: PodcastStudioProps) {
  return (
    <section aria-label="Podcast Intelligence Studio" className="space-y-5">
      <header>
        <h2 className="text-xl font-semibold">Podcast Intelligence Studio</h2>
        <p className="mt-1 text-sm text-muted-foreground">Build an optional, source-grounded audio overview. Production remains a separate confirmation.</p>
      </header>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <section className="rounded-md border p-4" aria-labelledby="podcast-studio-research-set">
          <h3 id="podcast-studio-research-set" className="font-semibold">Research Set</h3>
          <p className="mt-1 text-sm text-muted-foreground">{`${seedDocumentIds.length} selected document${seedDocumentIds.length === 1 ? '' : 's'}`} · references only, never source paths.</p>
        </section>
        <section className="rounded-md border p-4" aria-labelledby="podcast-studio-brief">
          <h3 id="podcast-studio-brief" className="font-semibold">Editorial Brief</h3>
          <p className="mt-1 text-sm text-muted-foreground">Briefing and model choices are reviewed before any production job is submitted.</p>
        </section>
      </div>
      <section className="rounded-md border p-4" aria-labelledby="podcast-studio-timeline">
        <h3 id="podcast-studio-timeline" className="font-semibold">Production Timeline</h3>
        <ol className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
          {timeline.map(([stage, detail]) => <li key={stage} className="rounded border bg-muted/30 p-2 text-sm"><span className="font-medium">{stage}</span><span className="mt-1 block text-xs text-muted-foreground">{detail}</span></li>)}
        </ol>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {['Evidence', 'Verification'].map(stage => <div key={stage} className="rounded border border-dashed p-3 text-sm"><span className="font-medium">{stage}</span><span className="mt-1 block text-xs text-muted-foreground">Available after intellectual engine upgrade</span></div>)}
        </div>
      </section>
      {modelPlans.length > 0 && <section className="rounded-md border p-4" aria-label="Model plan"><h3 className="font-semibold">Model Plan</h3><ul className="mt-2 grid gap-2 sm:grid-cols-2">{modelPlans.map(({ label, plan }) => <li key={label} className="text-sm"><span className="font-medium">{label}</span><span className="text-muted-foreground"> · {plan?.outcome ?? 'blocked'} · {plan?.reason ?? 'Route plan unavailable.'}</span></li>)}</ul></section>}
    </section>
  )
}

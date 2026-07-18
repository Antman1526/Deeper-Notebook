import { Badge } from '@/components/ui/badge'
import type { ResearchRun } from '@/lib/api/research'

const STAGES = ['plan', 'discover', 'await_source_approval', 'ingest', 'extract', 'compare', 'synthesize', 'validate', 'complete']

export function ResearchPlanPanel({ run }: { run: ResearchRun }) {
  const activeIndex = Math.max(STAGES.indexOf(run.stage), 0)
  return (
    <section aria-label="Research plan" className="rounded-md border bg-background p-4">
      <div className="flex flex-wrap items-start justify-between gap-2"><div><h2 className="text-sm font-semibold">Research plan</h2><p className="mt-1 text-sm text-muted-foreground">{run.objective}</p></div><Badge variant={run.cancelled ? 'destructive' : 'outline'}>{run.cancelled ? 'Cancelled' : run.stage.replaceAll('_', ' ')}</Badge></div>
      <ol className="mt-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {STAGES.map((stage, index) => <li key={stage} className={`rounded border px-2 py-1 text-xs ${index < activeIndex ? 'border-emerald-600/40 bg-emerald-500/5' : index === activeIndex ? 'border-primary bg-primary/5 font-medium' : 'text-muted-foreground'}`}>{stage.replaceAll('_', ' ')}</li>)}
      </ol>
      {run.hypotheses.length ? <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{run.hypotheses.map((hypothesis) => <li key={hypothesis}>{hypothesis}</li>)}</ul> : null}
    </section>
  )
}

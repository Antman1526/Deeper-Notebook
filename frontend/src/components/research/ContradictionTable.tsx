import { Badge } from '@/components/ui/badge'
import type { ResearchRun } from '@/lib/api/research'

export function ContradictionTable({ comparison }: { comparison: ResearchRun['comparison'] }) {
  const verdicts = comparison.verdicts ?? []
  if (!verdicts.length && !comparison.contradictions.length && !comparison.gaps.length) {
    return <section className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">Comparison results will appear after approved sources are extracted and validated.</section>
  }
  return <section aria-label="Evidence review" className="rounded-md border p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-sm font-semibold">Evidence review</h2><span className="text-xs text-muted-foreground">{verdicts.filter((verdict) => verdict.status === 'supported').length} supported claims</span></div>{verdicts.length ? <ul className="mt-3 space-y-3">{verdicts.map((verdict) => <li key={verdict.claim} className="border-l-2 border-primary/30 pl-3"><div className="flex flex-wrap items-center gap-2"><Badge variant={verdict.status === 'supported' ? 'secondary' : 'outline'}>{verdict.status}</Badge><p className="text-sm font-medium">{verdict.claim}</p></div><p className="mt-1 text-xs text-muted-foreground">{verdict.explanation}</p>{verdict.evidence.map((evidence) => <blockquote key={`${evidence.source_id}:${evidence.quote}`} className="mt-2 border-l pl-2 text-xs text-muted-foreground">{evidence.quote}{evidence.source_state === 'source_changed' ? ' (source changed)' : ''}</blockquote>)}</li>)}</ul> : null}{comparison.contradictions.length ? <p className="mt-3 text-sm text-destructive">{comparison.contradictions.length} contradiction{comparison.contradictions.length === 1 ? '' : 's'} need review.</p> : null}{comparison.gaps.length ? <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{comparison.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul> : null}</section>
}

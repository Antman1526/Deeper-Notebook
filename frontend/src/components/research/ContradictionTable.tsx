import type { ResearchRun } from '@/lib/api/research'

export function ContradictionTable({ comparison }: { comparison: ResearchRun['comparison'] }) {
  if (!comparison.contradictions.length && !comparison.gaps.length) return <section className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">Comparison results will appear after approved sources are extracted and validated.</section>
  return <section aria-label="Evidence differences" className="rounded-md border p-4"><h2 className="text-sm font-semibold">Evidence differences</h2>{comparison.contradictions.length ? <pre className="mt-3 max-h-44 overflow-auto rounded bg-muted p-3 text-xs">{JSON.stringify(comparison.contradictions, null, 2)}</pre> : null}{comparison.gaps.length ? <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{comparison.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul> : null}</section>
}

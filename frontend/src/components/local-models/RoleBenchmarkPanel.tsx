'use client'

import { CircleStop, Gauge, RotateCcw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { BenchmarkJob, BenchmarkResult, RoleRoute } from '@/lib/api/local-models'

const ROLES = [
  ['chat', 'Default chat'],
  ['source_synthesis', 'Source synthesis'],
  ['coding_research', 'Coding research'],
  ['study_fast', 'Fast study tools'],
] as const

export type RoleBenchmarkPanelProps = {
  routes?: RoleRoute[]
  benchmark?: BenchmarkJob
  onBenchmarkAll: () => void
  onBenchmarkRole: (role: string) => void
  onCancel?: () => void
  onReset?: () => void
  isStarting?: boolean
  isCancelling?: boolean
  isResetting?: boolean
}

function hasQualityMeasurement(result: BenchmarkResult) {
  return Boolean(result.quality && Object.values(result.quality).some(value => typeof value === 'boolean'))
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-muted-foreground">{label}</dt><dd className="font-mono">{value}</dd></div>
}

function ResultRow({ result }: { result: BenchmarkResult }) {
  const qualityMeasured = hasQualityMeasurement(result)
  const metrics = result.normalized_metrics ?? {}
  return <div className="rounded-md border px-3 py-3" data-testid={`benchmark-${result.role}`}>
    <div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-sm font-medium">{result.label}</p><p className="font-mono text-xs text-muted-foreground">{result.model_name ?? result.error ?? result.status}</p></div><Badge variant={result.status === 'completed' ? 'secondary' : 'outline'}>{result.status}</Badge></div>
    {result.status === 'completed' && <><dl className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4"><Metric label="Quality score" value={qualityMeasured ? `${result.score.toFixed(1)} / 100` : 'Not measured'} /><Metric label="Speed" value={result.tokens_per_second ? `${result.tokens_per_second.toFixed(0)} tok/s` : 'Unknown'} /><Metric label="Latency" value={result.latency_ms ? `${result.latency_ms} ms` : 'Unknown'} /><Metric label="Raw checks" value={qualityMeasured ? `${Object.keys(metrics).filter(key => !['latency', 'throughput'].includes(key)).length} measured` : 'Speed only'} /></dl>{qualityMeasured ? <p className="mt-2 text-xs text-muted-foreground">Quality combines role-specific checks with latency. Raw normalized signals: {Object.entries(metrics).map(([key, value]) => `${key} ${Math.round(value)}`).join(', ') || 'not returned'}.</p> : <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">Speed-only legacy result. It is not eligible as a quality winner until this role is benchmarked again.</p>}</>}
  </div>
}

export function RoleBenchmarkPanel({ routes = [], benchmark, onBenchmarkAll, onBenchmarkRole, onCancel, onReset, isStarting, isCancelling, isResetting }: RoleBenchmarkPanelProps) {
  const running = benchmark?.status === 'queued' || benchmark?.status === 'running'
  const controls = benchmark?.controls
  return <Card data-testid="local-model-benchmarks">
    <CardHeader className="pb-3"><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle className="flex items-center gap-2 text-base"><Gauge className="h-4 w-4" />Measured model roles</CardTitle><CardDescription>Quality checks choose local models by role. A speed-only reading never counts as a quality result.</CardDescription></div><div className="flex gap-2"><Button disabled={isStarting || running} onClick={onBenchmarkAll} size="sm"><Gauge className="h-3.5 w-3.5" />Benchmark all roles</Button>{running && controls?.cancel && <Button disabled={isCancelling} onClick={onCancel} size="sm" variant="outline"><CircleStop className="h-3.5 w-3.5" />Cancel</Button>}{!running && controls?.reset && <Button disabled={isResetting} onClick={onReset} size="sm" variant="ghost"><RotateCcw className="h-3.5 w-3.5" />Reset</Button>}</div></div></CardHeader>
    <CardContent className="space-y-4"><div className="grid gap-2 sm:grid-cols-2">{ROLES.map(([role, label]) => { const route = routes.find(item => item.role === role); return <div className="flex min-w-0 flex-col items-stretch gap-2 rounded-md border px-3 py-2 sm:flex-row sm:items-center sm:justify-between" key={role}><div className="min-w-0"><p className="text-sm font-medium">{label}</p><p className="truncate text-xs text-muted-foreground">{route?.model?.name ?? 'No eligible local model'}</p></div><Button aria-label={`Benchmark ${label}`} className="w-full sm:w-auto" disabled={isStarting || running} onClick={() => onBenchmarkRole(role)} size="sm" variant="outline">Benchmark</Button></div> })}</div>{benchmark ? <div className="space-y-2" data-testid="local-model-benchmark-results">{benchmark.results.length ? benchmark.results.map(result => <ResultRow key={`${benchmark.job_id}-${result.role}`} result={result} />) : <p className="text-sm text-muted-foreground">Benchmark queued. Results will appear here.</p>}</div> : <p className="text-sm text-muted-foreground">No quality measurement has been run yet.</p>}</CardContent>
  </Card>
}

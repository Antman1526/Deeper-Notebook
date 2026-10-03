'use client'

import { CircleStop, Gauge, RotateCcw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { BenchmarkJob, BenchmarkResult, RoleRoute } from '@/lib/api/local-models'
import { useTranslation } from '@/lib/hooks/use-translation'

const ROLES = [
  ['chat', 'settings.roleBenchmarkPanel.roleChat'],
  ['source_synthesis', 'settings.roleBenchmarkPanel.roleSourceSynthesis'],
  ['coding_research', 'settings.roleBenchmarkPanel.roleCodingResearch'],
  ['study_fast', 'settings.roleBenchmarkPanel.roleStudyFast'],
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

// v0.8.130 — status colours from theme tokens (UI audit Phase 1)
function ResultRow({ result }: { result: BenchmarkResult }) {
  const { t } = useTranslation()
  const qualityMeasured = hasQualityMeasurement(result)
  const metrics = result.normalized_metrics ?? {}
  return <div className="rounded-md border px-3 py-3" data-testid={`benchmark-${result.role}`}>
    <div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-sm font-medium">{result.label}</p><p className="font-mono text-xs text-muted-foreground">{result.model_name ?? result.error ?? result.status}</p></div><Badge variant={result.status === 'completed' ? 'secondary' : 'outline'}>{result.status}</Badge></div>
    {result.status === 'completed' && <><dl className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4"><Metric label={t('settings.roleBenchmarkPanel.qualityScore')} value={qualityMeasured ? t('settings.roleBenchmarkPanel.scoreOutOf100', { score: result.score.toFixed(1) }) : t('settings.roleBenchmarkPanel.notMeasured')} /><Metric label={t('settings.roleBenchmarkPanel.speed')} value={result.tokens_per_second ? t('settings.roleBenchmarkPanel.tokensPerSecond', { value: result.tokens_per_second.toFixed(0) }) : t('common.unknown')} /><Metric label={t('settings.roleBenchmarkPanel.latency')} value={result.latency_ms ? t('settings.roleBenchmarkPanel.latencyMs', { value: result.latency_ms }) : t('common.unknown')} /><Metric label={t('settings.roleBenchmarkPanel.rawChecks')} value={qualityMeasured ? t('settings.roleBenchmarkPanel.checksMeasured', { count: Object.keys(metrics).filter(key => !['latency', 'throughput'].includes(key)).length }) : t('settings.roleBenchmarkPanel.speedOnly')} /></dl>{qualityMeasured ? <p className="mt-2 text-xs text-muted-foreground">{t('settings.roleBenchmarkPanel.qualityCombines', { signals: Object.entries(metrics).map(([key, value]) => `${key} ${Math.round(value)}`).join(', ') || t('settings.roleBenchmarkPanel.notReturned') })}</p> : <p className="mt-2 text-xs text-warning-ink">{t('settings.roleBenchmarkPanel.speedOnlyLegacy')}</p>}</>}
  </div>
}

export function RoleBenchmarkPanel({ routes = [], benchmark, onBenchmarkAll, onBenchmarkRole, onCancel, onReset, isStarting, isCancelling, isResetting }: RoleBenchmarkPanelProps) {
  const { t } = useTranslation()
  const running = benchmark?.status === 'queued' || benchmark?.status === 'running'
  const controls = benchmark?.controls
  return <Card data-testid="local-model-benchmarks">
    <CardHeader className="pb-3"><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle className="flex items-center gap-2 text-base"><Gauge className="h-4 w-4" />{t('settings.roleBenchmarkPanel.title')}</CardTitle><CardDescription>{t('settings.roleBenchmarkPanel.description')}</CardDescription></div><div className="flex gap-2"><Button disabled={isStarting || running} onClick={onBenchmarkAll} size="sm"><Gauge className="h-3.5 w-3.5" />{t('settings.roleBenchmarkPanel.benchmarkAll')}</Button>{running && controls?.cancel && <Button disabled={isCancelling} onClick={onCancel} size="sm" variant="outline"><CircleStop className="h-3.5 w-3.5" />{t('common.cancel')}</Button>}{!running && controls?.reset && <Button disabled={isResetting} onClick={onReset} size="sm" variant="ghost"><RotateCcw className="h-3.5 w-3.5" />{t('settings.roleBenchmarkPanel.reset')}</Button>}</div></div></CardHeader>
    <CardContent className="space-y-4"><div className="grid gap-2 sm:grid-cols-2">{ROLES.map(([role, labelKey]) => { const label = t(labelKey); const route = routes.find(item => item.role === role); return <div className="flex min-w-0 flex-col items-stretch gap-2 rounded-md border px-3 py-2 sm:flex-row sm:items-center sm:justify-between" key={role}><div className="min-w-0"><p className="text-sm font-medium">{label}</p><p className="truncate text-xs text-muted-foreground">{route?.model?.name ?? t('settings.roleBenchmarkPanel.noEligibleModel')}</p></div><Button aria-label={t('settings.roleBenchmarkPanel.benchmarkRoleAria', { label })} className="w-full sm:w-auto" disabled={isStarting || running} onClick={() => onBenchmarkRole(role)} size="sm" variant="outline">{t('settings.roleBenchmarkPanel.benchmark')}</Button></div> })}</div>{benchmark ? <div className="space-y-2" data-testid="local-model-benchmark-results">{benchmark.results.length ? benchmark.results.map(result => <ResultRow key={`${benchmark.job_id}-${result.role}`} result={result} />) : <p className="text-sm text-muted-foreground">{t('settings.roleBenchmarkPanel.queued')}</p>}</div> : <p className="text-sm text-muted-foreground">{t('settings.roleBenchmarkPanel.noMeasurement')}</p>}</CardContent>
  </Card>
}

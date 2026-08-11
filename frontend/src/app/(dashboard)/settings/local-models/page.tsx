'use client'

import React from 'react'
import { AlertCircle, Cpu, Loader2 } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { DownloadPanel } from './DownloadPanel'
import { LocalExecutionPolicyPanel } from '@/components/local-models/LocalExecutionPolicyPanel'
import { ModelRoutePlanPanel } from '@/components/local-models/ModelRoutePlanPanel'
import { ModelInventory } from '@/components/local-models/ModelInventory'
import { RoleBenchmarkPanel } from '@/components/local-models/RoleBenchmarkPanel'
import { RouteReceiptPanel } from '@/components/local-models/RouteReceiptPanel'
import { SidecarLogPopover, sidecarKindFromName } from '@/components/chat/SidecarLogPopover'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AppShell } from '@/components/layout/AppShell'
import type {
  BenchmarkJob,
  BenchmarkListResponse,
  InventoryResponse,
  LocalModelSettings,
  LocalModel,
  ReadinessResponse,
  RouteReceiptResponse,
} from '@/lib/api/local-models'
import {
  getLocalModelInventory,
  getLocalModelReadiness,
  getLocalModelSettings,
  getRouteReceipts,
  updateLocalModelSettings,
} from '@/lib/api/local-models'
import apiClient from '@/lib/api/client'
import { useLocalModelsHealth, useModelRoutePlan } from '@/lib/hooks/use-local-models'
import { SystemRouteFrame } from '@/components/deeper-notebook/route-frames/SystemRouteFrames'

const BENCHMARK_ROLES = ['chat', 'source_synthesis', 'coding_research', 'study_fast']

function ConnectionChecks() {
  const health = useLocalModelsHealth()
  const checks = health.data?.models ?? []
  if (!checks.length) return null

  return (
    <Card data-testid="local-model-connection-checks">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Connection checks</CardTitle>
        <CardDescription>Live status from registered local runtimes.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Badge variant={health.data?.overall === 'healthy' ? 'secondary' : 'outline'}>{health.data?.overall ?? 'checking'}</Badge>
        {checks.map(check => <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-2 text-xs" key={`${check.runtime}-${check.name}`}>
          <div><span className="font-medium">{check.name}</span>{check.runtime && <span className="ml-2 text-muted-foreground">{check.runtime}</span>}<div className="mt-1 break-all text-muted-foreground">{check.endpoint} {check.probe_path}</div>{check.detail && <div className="mt-1 text-muted-foreground">{check.detail}</div>}</div>
          {check.status !== 'healthy' && sidecarKindFromName(check.name) && <SidecarLogPopover kind={sidecarKindFromName(check.name)!}><Button aria-label={`View log and restart ${check.name}`} size="sm" variant="outline">View log / Restart</Button></SidecarLogPopover>}
        </div>)}
      </CardContent>
    </Card>
  )
}

function LocalModelsWorkspace() {
  const queryClient = useQueryClient()
  const inventory = useQuery<InventoryResponse>({
    queryKey: ['local-models', 'inventory'],
    queryFn: getLocalModelInventory,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  })
  const health = useLocalModelsHealth()
  const hasRunnableModels = inventory.data?.models.some(model => model.runnable ?? ['gguf', 'mlx'].includes(model.runtime ?? '')) ?? false
  const settings = useQuery<LocalModelSettings>({ queryKey: ['local-models', 'settings'], queryFn: getLocalModelSettings })
  const readiness = useQuery<ReadinessResponse>({ queryKey: ['local-models', 'readiness'], queryFn: getLocalModelReadiness, enabled: hasRunnableModels })
  const researchChatPlan = useModelRoutePlan(settings.data ? {
    role: 'research_chat', execution_policy: settings.data.execution_policy, compute_profile: settings.data.compute_profile,
    role_override_model_id: settings.data.role_overrides.research_chat ?? null, modalities: ['text'],
  } : null)
  const embeddingPlan = useModelRoutePlan(settings.data ? {
    role: 'embedding_retrieval', execution_policy: settings.data.execution_policy, compute_profile: settings.data.compute_profile,
    role_override_model_id: settings.data.role_overrides.embedding_retrieval ?? null, modalities: ['text'],
  } : null)
  const [approvedCloudContinuation, setApprovedCloudContinuation] = React.useState<string | null>(null)
  const cloudFallback = settings.data?.execution_policy === 'local_preferred'
    ? researchChatPlan.data?.outcome === 'approval_required'
      ? { stage: 'Research Chat', contentClass: 'Selected knowledge' }
      : embeddingPlan.data?.outcome === 'approval_required'
        ? { stage: 'Embedding Retrieval', contentClass: 'Knowledge index' }
        : null
    : null
  const cloudFallbackKey = cloudFallback ? `${cloudFallback.stage}:${cloudFallback.contentClass}` : null
  const pendingCloudRoute = cloudFallback && cloudFallbackKey !== approvedCloudContinuation ? cloudFallback : null
  const benchmarks = useQuery<BenchmarkListResponse>({
    queryKey: ['local-models', 'benchmarks'],
    queryFn: async () => (await apiClient.get<BenchmarkListResponse>('/local-models/benchmarks')).data,
    enabled: hasRunnableModels,
  })
  const receipts = useQuery<RouteReceiptResponse>({
    queryKey: ['local-models', 'route-receipts'],
    queryFn: getRouteReceipts,
    enabled: hasRunnableModels,
    retry: false,
  })
  const benchmark = useMutation({
    mutationFn: async (roles: string[]) => (await apiClient.post<BenchmarkJob>('/local-models/benchmarks', { roles })).data,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['local-models', 'benchmarks'] }),
  })
  const cancel = useMutation({
    mutationFn: async (jobId: string) => (await apiClient.post<BenchmarkJob>(`/local-models/benchmarks/${jobId}/cancel`)).data,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['local-models', 'benchmarks'] }),
  })
  const reset = useMutation({
    mutationFn: async () => apiClient.delete('/local-models/benchmarks'),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['local-models', 'benchmarks'] }),
  })
  const saveSettings = useMutation({
    mutationFn: updateLocalModelSettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['local-models', 'settings'] })
      void queryClient.invalidateQueries({ queryKey: ['local-models', 'inventory'] })
      void queryClient.invalidateQueries({ queryKey: ['local-models', 'readiness'] })
    },
  })
  const [activatingPath, setActivatingPath] = React.useState<string | null>(null)
  const [launchDefaultRef, setLaunchDefaultRef] = React.useState<string | null>(null)
  const currentBenchmark = benchmark.data ?? benchmarks.data?.benchmarks?.[0]

  const setActive = async (model: LocalModel) => {
    setActivatingPath(model.path)
    try {
      const response = await apiClient.post<{ ok: boolean; detail: string }>('/local-models/set-active', { path: model.path })
      if (response.data.ok) {
        toast.success(`Active chat model switched: ${response.data.detail}`)
        await inventory.refetch()
      } else toast.error(`Could not switch chat model: ${response.data.detail}`)
    } catch (error) {
      toast.error(`Could not switch chat model: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setActivatingPath(null)
    }
  }

  const setLaunchDefault = async (model: LocalModel) => {
    if (!model.launcher_model_ref) return
    setLaunchDefaultRef(model.launcher_model_ref)
    try {
      const response = await apiClient.post<{ ok: boolean; detail: string }>('/local-models/launch-default', { launcher_model_ref: model.launcher_model_ref })
      if (response.data.ok) {
        toast.success('Native launcher default saved. Restart Deeper Notebook to apply it.')
        await inventory.refetch()
      } else toast.error(response.data.detail)
    } catch (error) {
      toast.error(`Could not set launch default: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setLaunchDefaultRef(null)
    }
  }

  return <div className="mx-auto max-w-6xl space-y-6 px-6 py-8 sm:px-8">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="max-w-3xl space-y-2"><h2 className="flex items-center gap-3 text-3xl font-semibold"><Cpu className="h-7 w-7" />Local model roles</h2><p className="text-muted-foreground">Inspect installed models, measure them for the work they do, and keep every routing decision local and explainable.</p></div>
      {inventory.isFetching && <span className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Refreshing</span>}
    </header>

    <ConnectionChecks />
    {readiness.isError && <Alert><AlertCircle className="h-4 w-4" /><AlertTitle>Local readiness is unavailable</AlertTitle><AlertDescription>The inventory remains available. Automatic routing stays fail-closed until readiness can be read.</AlertDescription></Alert>}
    <SettingsReadinessPanels
      inventory={inventory.data}
      readiness={readiness.data}
      readinessError={readiness.isError}
      settings={settings.data}
      settingsError={settings.isError}
      onRescan={() => { void inventory.refetch(); void readiness.refetch() }}
      onSave={next => settings.data && saveSettings.mutate({ ...settings.data, ...next }, { onError: () => toast.error('Could not save local execution settings.') })}
      isSaving={saveSettings.isPending}
      researchPlan={researchChatPlan.data}
      embeddingPlan={embeddingPlan.data}
      routePlansError={researchChatPlan.isError || embeddingPlan.isError}
      pendingCloudRoute={pendingCloudRoute}
      cloudContinuationRecorded={Boolean(cloudFallbackKey && cloudFallbackKey === approvedCloudContinuation)}
      onConfirmCloudRoute={route => setApprovedCloudContinuation(`${route.stage}:${route.contentClass}`)}
    />
    <RoleBenchmarkPanel
      benchmark={currentBenchmark}
      isCancelling={cancel.isPending}
      isResetting={reset.isPending}
      isStarting={benchmark.isPending}
      onBenchmarkAll={() => benchmark.mutate(BENCHMARK_ROLES)}
      onBenchmarkRole={role => benchmark.mutate([role])}
      onCancel={() => currentBenchmark && cancel.mutate(currentBenchmark.job_id, { onError: () => toast.error('This desktop runtime cannot cancel the running benchmark.') })}
      onReset={() => reset.mutate(undefined, { onError: () => toast.error('This desktop runtime cannot reset benchmark history.') })}
      routes={[]}
    />
    <RouteReceiptPanel isError={receipts.isError} isLoading={receipts.isLoading} receipts={receipts.data?.receipts ?? []} />
    <ModelInventory
      activatingPath={activatingPath}
      health={health.data?.models ?? []}
      inventory={inventory.data}
      isError={inventory.isError}
      isLoading={inventory.isLoading}
      onRefresh={() => void inventory.refetch()}
      onSetActive={setActive}
      onSetLaunchDefault={setLaunchDefault}
      settingLaunchDefaultRef={launchDefaultRef}
    />
    <DownloadPanel />
  </div>
}

function SettingsReadinessPanels({ inventory, readiness, readinessError, settings, settingsError, onRescan, onSave, isSaving, researchPlan, embeddingPlan, routePlansError, pendingCloudRoute, cloudContinuationRecorded, onConfirmCloudRoute }: {
  inventory?: InventoryResponse; readiness?: ReadinessResponse; readinessError: boolean; settings?: LocalModelSettings; settingsError: boolean
  onRescan: () => void; onSave: (next: Pick<LocalModelSettings, 'execution_policy' | 'compute_profile' | 'local_model_memory_limit_bytes'>) => void; isSaving: boolean
  researchPlan?: import('@/lib/api/local-models').ModelRoutePlan; embeddingPlan?: import('@/lib/api/local-models').ModelRoutePlan; routePlansError: boolean
  pendingCloudRoute: { stage: string; contentClass: string } | null; cloudContinuationRecorded: boolean; onConfirmCloudRoute: (route: { stage: string; contentClass: string }) => void
}) {
  const models = readiness?.models ?? []
  const grouped = models.reduce<Record<string, number>>((result, model) => ({ ...result, [model.readiness]: (result[model.readiness] ?? 0) + 1 }), {})
  const accepted = models.filter(model => model.route_eligible)
  const tiers = accepted.reduce<Record<string, number>>((result, model) => ({ ...result, [model.measured_tier ?? 'unmeasured']: (result[model.measured_tier ?? 'unmeasured'] ?? 0) + 1 }), {})
  return <>
    <Card data-testid="local-model-library"><CardHeader className="pb-3"><CardTitle className="text-base">Model library and rescan</CardTitle><CardDescription>Inventory is read-only. Canonical paths are shown only in the dedicated inventory below.</CardDescription></CardHeader><CardContent className="space-y-2 text-sm"><p>{inventory?.available ? 'Library available' : 'Library unavailable'}</p><Button onClick={onRescan} size="sm" type="button" variant="outline">Rescan local library</Button></CardContent></Card>
    <div className="grid gap-4 lg:grid-cols-2">
      <Card data-testid="local-model-readiness"><CardHeader className="pb-3"><CardTitle className="text-base">Readiness and runtime compatibility</CardTitle><CardDescription>Only ready verified models are eligible for automatic routes.</CardDescription></CardHeader><CardContent>{readinessError ? <p role="status">Readiness unavailable — automatic routing is blocked.</p> : models.length ? <ul className="space-y-1 text-sm">{Object.entries(grouped).map(([state, count]) => <li key={state}>{state.replace(/_/g, ' ')}: {count}</li>)}</ul> : <p className="text-sm text-muted-foreground">No route-safe readiness facts are available.</p>}</CardContent></Card>
      <Card data-testid="local-model-route-overrides"><CardHeader className="pb-3"><CardTitle className="text-base">Role routes and overrides</CardTitle><CardDescription>Overrides are explicit and rejected when a model fails readiness, quality, context, or memory gates.</CardDescription></CardHeader><CardContent className="space-y-2 text-sm"><p>{Object.keys(settings?.role_overrides ?? {}).length} configured role override(s)</p>{accepted.length ? <ul>{accepted.slice(0, 8).map(model => <li key={model.model_id}><code>{model.model_id}</code> · {model.accepted_roles.join(', ') || 'no accepted role'}</li>)}</ul> : <p className="text-muted-foreground">No verified local route is currently available.</p>}</CardContent></Card>
      <Card data-testid="local-model-tiers"><CardHeader className="pb-3"><CardTitle className="text-base">Measured tiers and memory</CardTitle><CardDescription>Balanced selects the smallest accepted model that clears all gates.</CardDescription></CardHeader><CardContent className="text-sm">{Object.entries(tiers).length ? Object.entries(tiers).map(([tier, count]) => <p key={tier}>{tier}: {count}</p>) : <p className="text-muted-foreground">No accepted benchmark tier yet.</p>}</CardContent></Card>
      <ModelRoutePlanPanel title="Research Chat route" plan={researchPlan} isError={readinessError || settingsError || routePlansError} />
      <ModelRoutePlanPanel title="Embedding route" plan={embeddingPlan} isError={readinessError || settingsError || routePlansError} />
    </div>
    {settings ? <><LocalExecutionPolicyPanel policy={settings.execution_policy} computeProfile={settings.compute_profile} memoryLimitBytes={settings.local_model_memory_limit_bytes} pendingCloudRoute={pendingCloudRoute} onConfirmCloudRoute={onConfirmCloudRoute} isSaving={isSaving} onSave={onSave} />{cloudContinuationRecorded && <p role="status" className="text-sm text-muted-foreground">Cloud continuation recorded for this exact route. No task has been executed.</p>}</> : <Card><CardContent className="py-5 text-sm text-muted-foreground">Loading local execution settings…</CardContent></Card>}
  </>
}

export default function LocalModelsPage() {
  return <AppShell><SystemRouteFrame route="/settings/local-models"><LocalModelsWorkspace /></SystemRouteFrame></AppShell>
}

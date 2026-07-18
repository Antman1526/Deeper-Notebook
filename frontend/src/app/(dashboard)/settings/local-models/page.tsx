'use client'

import React from 'react'
import { AlertCircle, Cpu, Loader2 } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { DownloadPanel } from './DownloadPanel'
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
  LocalModel,
  RoleRoutingResponse,
  RouteReceiptResponse,
} from '@/lib/api/local-models'
import apiClient from '@/lib/api/client'
import { useLocalModelsHealth } from '@/lib/hooks/use-local-models'

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
    queryFn: async () => (await apiClient.get<InventoryResponse>('/local-models/inventory')).data,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  })
  const health = useLocalModelsHealth()
  const hasRunnableModels = inventory.data?.models.some(model => model.runnable ?? ['gguf', 'mlx'].includes(model.runtime ?? '')) ?? false
  const routing = useQuery<RoleRoutingResponse>({
    queryKey: ['local-models', 'role-routing'],
    queryFn: async () => (await apiClient.get<RoleRoutingResponse>('/local-models/role-routing')).data,
    enabled: hasRunnableModels,
  })
  const benchmarks = useQuery<BenchmarkListResponse>({
    queryKey: ['local-models', 'benchmarks'],
    queryFn: async () => (await apiClient.get<BenchmarkListResponse>('/local-models/benchmarks')).data,
    enabled: hasRunnableModels,
  })
  const receipts = useQuery<RouteReceiptResponse>({
    queryKey: ['local-models', 'route-receipts'],
    queryFn: async () => (await apiClient.get<RouteReceiptResponse>('/local-models/route-receipts')).data,
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
        toast.success('Native launcher default saved. Restart Open Notebook Plus to apply it.')
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
      <div className="max-w-3xl space-y-2"><h1 className="flex items-center gap-3 text-3xl font-semibold"><Cpu className="h-7 w-7" />Local model roles</h1><p className="text-muted-foreground">Inspect installed models, measure them for the work they do, and keep every routing decision local and explainable.</p></div>
      {inventory.isFetching && <span className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Refreshing</span>}
    </header>

    <ConnectionChecks />
    {routing.isError && <Alert><AlertCircle className="h-4 w-4" /><AlertTitle>Role recommendations are unavailable</AlertTitle><AlertDescription>The inventory remains available. Benchmarking will resume when the local routing service is reachable.</AlertDescription></Alert>}
    <RoleBenchmarkPanel
      benchmark={currentBenchmark}
      isCancelling={cancel.isPending}
      isResetting={reset.isPending}
      isStarting={benchmark.isPending}
      onBenchmarkAll={() => benchmark.mutate(BENCHMARK_ROLES)}
      onBenchmarkRole={role => benchmark.mutate([role])}
      onCancel={() => currentBenchmark && cancel.mutate(currentBenchmark.job_id, { onError: () => toast.error('This desktop runtime cannot cancel the running benchmark.') })}
      onReset={() => reset.mutate(undefined, { onError: () => toast.error('This desktop runtime cannot reset benchmark history.') })}
      routes={routing.data?.routes}
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

export default function LocalModelsPage() {
  return <AppShell><div className="flex-1 overflow-y-auto"><LocalModelsWorkspace /></div></AppShell>
}

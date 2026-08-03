'use client'

import React from 'react'
import { Copy, FolderOpen, RefreshCw, Search } from 'lucide-react'
import { toast } from 'sonner'

import { ModelFleetBadge } from '@/components/deeper-notebook/ModelFleetBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import type { InventoryResponse, LocalModel } from '@/lib/api/local-models'
import type { LocalModelHealth } from '@/lib/hooks/use-local-models'

type InventoryFilter = 'all' | 'ready' | 'needs-setup'
type InventorySort = 'name' | 'quality-ready' | 'size' | 'context'

export type ModelInventoryProps = {
  inventory?: InventoryResponse
  health: LocalModelHealth[]
  isLoading?: boolean
  isError?: boolean
  onRefresh: () => void
  onSetActive?: (model: LocalModel) => void
  onSetLaunchDefault?: (model: LocalModel) => void
  activatingPath?: string | null
  settingLaunchDefaultRef?: string | null
}

const formatBytes = (value: number) => {
  if (!value) return 'Unknown'
  const gigabytes = value / 1024 ** 3
  return gigabytes >= 1 ? `${gigabytes.toFixed(1)} GB` : `${Math.round(value / 1024 ** 2)} MB`
}

const formatContext = (value: number | null) => value && value >= 1024
  ? `${Math.round(value / 1024)}k` : value?.toString() ?? 'Unknown'

function canRun(model: LocalModel) {
  return model.runnable ?? ['gguf', 'mlx'].includes(model.runtime ?? '')
}

function matchingHealth(model: LocalModel, health: LocalModelHealth[]) {
  const name = model.name.toLowerCase()
  return health.find(item => name.includes(item.name.toLowerCase()) || item.name.toLowerCase().includes(name))
}

function ModelRow({
  model,
  health,
  onSetActive,
  onSetLaunchDefault,
  activatingPath,
  settingLaunchDefaultRef,
}: Omit<ModelInventoryProps, 'inventory' | 'isLoading' | 'isError' | 'onRefresh'> & { model: LocalModel }) {
  const runtimeHealth = matchingHealth(model, health)
  const copyPath = async () => {
    try {
      await navigator.clipboard.writeText(model.path)
      toast.success('Model path copied')
    } catch {
      toast.error('Could not copy model path')
    }
  }
  const runnerReady = canRun(model)
  const canActivate = Boolean(model.activation_supported ?? model.runtime === 'gguf')
  const canSetDefault = Boolean(model.launcher_model_ref && runnerReady)

  return (
    <Card data-testid={`local-model-${model.name}`}>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <CardTitle className="break-all text-base">{model.name}</CardTitle>
            <CardDescription className="flex items-center gap-1 break-all text-xs">
              <span>{model.path}</span>
              <Button aria-label={`Copy model path for ${model.name}`} className="h-6 w-6 shrink-0" onClick={copyPath} size="icon" variant="ghost">
                <Copy className="h-3 w-3" />
              </Button>
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <ModelFleetBadge runtime={model.runtime} />
            <Badge variant={runnerReady ? 'secondary' : 'outline'}>{runnerReady ? 'Available' : 'Setup needed'}</Badge>
            {model.readiness && <Badge variant={model.route_eligible ? 'secondary' : 'outline'}>{model.readiness.replace(/_/g, ' ')}</Badge>}
            {model.measured_tier && <Badge variant="outline">{model.measured_tier} tier</Badge>}
            {runtimeHealth && <Badge variant={runtimeHealth.status === 'healthy' ? 'secondary' : 'outline'}>{runtimeHealth.status}</Badge>}
            {model.is_live_active && <Badge>Active</Badge>}
            {model.is_launch_default && <Badge variant="secondary">Launch default</Badge>}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-5">
          <Metric label="Runtime" value={model.runtime?.toUpperCase() ?? 'Local'} />
          <Metric label="Size" value={formatBytes(model.file_size_bytes)} />
          <Metric label="Context" value={formatContext(model.context_length)} />
          <Metric label="Parameters" value={model.parameter_count_b ? `${model.parameter_count_b}B` : 'Unknown'} />
          <Metric label="Capability" value={runnerReady ? 'Runnable' : 'Inventory only'} />
        </dl>
        {!runnerReady && <p className="border-l-2 border-muted-foreground/30 pl-3 text-xs text-muted-foreground">{model.runtime_note ?? 'This asset is visible for curation, but no compatible local runtime is registered.'}</p>}
        {model.readiness_reason && <p className="text-xs text-muted-foreground">{model.readiness_reason}</p>}
        {model.accepted_roles?.length ? <p className="text-xs text-muted-foreground">Accepted roles: {model.accepted_roles.join(', ')}</p> : null}
        {(canActivate || canSetDefault) && <div className="flex flex-wrap justify-end gap-2">
          {canSetDefault && <Button disabled={Boolean(model.is_launch_default) || settingLaunchDefaultRef === model.launcher_model_ref} onClick={() => onSetLaunchDefault?.(model)} size="sm" variant="outline">Set launch default</Button>}
          {canActivate && <Button data-testid={`set-active-${model.name}`} disabled={activatingPath === model.path} onClick={() => onSetActive?.(model)} size="sm" variant="outline">{activatingPath === model.path ? 'Switching...' : 'Switch live chat model'}</Button>}
        </div>}
      </CardContent>
    </Card>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-muted-foreground">{label}</dt><dd className="mt-0.5 font-mono">{value}</dd></div>
}

export function ModelInventory({ inventory, health, isLoading, isError, onRefresh, ...actions }: ModelInventoryProps) {
  const [filter, setFilter] = React.useState<InventoryFilter>('all')
  const [sort, setSort] = React.useState<InventorySort>('name')
  const [search, setSearch] = React.useState('')
  const models = inventory?.models ?? []
  const visibleModels = models.filter(model => {
    const searchable = `${model.name} ${model.runtime} ${model.quant} ${model.architecture}`.toLowerCase()
    return (filter === 'all' || (filter === 'ready' ? canRun(model) : !canRun(model)))
      && searchable.includes(search.toLowerCase())
  }).sort((left, right) => {
    if (sort === 'size') return right.file_size_bytes - left.file_size_bytes
    if (sort === 'context') return (right.context_length ?? 0) - (left.context_length ?? 0)
    if (sort === 'quality-ready') return Number(canRun(right)) - Number(canRun(left)) || left.name.localeCompare(right.name)
    return left.name.localeCompare(right.name)
  })

  if (isLoading) return <Card><CardContent className="py-8 text-sm text-muted-foreground">Reading local model inventory...</CardContent></Card>
  if (isError) return <Card><CardContent className="py-8 text-sm text-destructive">The model inventory could not be loaded. Refresh to try again.</CardContent></Card>
  if (!inventory?.available) return <Card><CardContent className="py-8 text-sm text-muted-foreground">Model directory not found. Configure the desktop launcher, then refresh this page.</CardContent></Card>

  return (
    <section className="space-y-3" data-testid="local-models-list">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 text-xs text-muted-foreground"><FolderOpen className="mr-1 inline h-3 w-3" /><code className="break-all">{inventory.model_dir}</code></div>
        <Button onClick={onRefresh} size="sm" variant="outline"><RefreshCw className="h-3.5 w-3.5" />Refresh</Button>
      </div>
      {models.length === 0 ? <Card><CardContent className="py-8 text-sm text-muted-foreground">No models installed yet. Browse on HuggingFace or add a local model through the launcher.</CardContent></Card> : <>
        <div className="flex flex-wrap gap-2">
          <div className="relative min-w-48 flex-1"><Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" /><Input aria-label="Search local models" className="pl-8" onChange={event => setSearch(event.target.value)} placeholder="Search models" value={search} /></div>
          <select aria-label="Filter local model inventory" className="rounded-md border bg-background px-3 text-sm" onChange={event => setFilter(event.target.value as InventoryFilter)} value={filter}><option value="all">All models</option><option value="ready">Ready</option><option value="needs-setup">Setup needed</option></select>
          <select aria-label="Sort local models" className="rounded-md border bg-background px-3 text-sm" onChange={event => setSort(event.target.value as InventorySort)} value={sort}><option value="name">Name</option><option value="quality-ready">Availability</option><option value="size">Size</option><option value="context">Context</option></select>
        </div>
        {visibleModels.length ? visibleModels.map(model => <ModelRow key={model.path} model={model} health={health} {...actions} />) : <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">No models match the current filters.</CardContent></Card>}
      </>}
    </section>
  )
}

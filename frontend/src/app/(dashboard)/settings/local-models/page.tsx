'use client'

/**
 * Settings → Local Models page (v0.8.39 Phase 4a — read-only inventory).
 *
 * Lists every GGUF in the configured model directory with metadata
 * (architecture, parameter count, quant, context length, file size).
 * Empty state guides the user to drop GGUFs into the configured path.
 *
 * Future (deferred to v0.8.39b / v0.8.39c):
 *   - "Download" panel with curated HuggingFace recommendations.
 *   - "Set Active" button to hot-swap the chat sidecar's GGUF without
 *     relaunching.
 */

import React from 'react'
import Link from 'next/link'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import {
  BookOpenCheck,
  BrainCircuit,
  Code2,
  Cpu,
  Database,
  FolderOpen,
  Gauge,
  GraduationCap,
  Hash,
  HardDrive,
  RefreshCw,
  AlertCircle,
  Download,
  Sparkles,
  Power,
  Loader2,
  Search,
  Copy,
  FilePlus,
  Settings2,
  CircleStop,
} from 'lucide-react'
import { toast } from 'sonner'
import { AppShell } from '@/components/layout/AppShell'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ModelFleetBadge } from '@/components/onp'
import { SmartRoutingPanel } from '@/components/settings/SmartRoutingPanel'
import apiClient from '@/lib/api/client'
import { useAutoAssignCapability, useModelDefaults, useModels } from '@/lib/hooks/use-models'
import { useLocalModelsHealth } from '@/lib/hooks/use-local-models'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { Model, ModelDefaults } from '@/lib/types/models'
// v0.8.39b — curated HuggingFace recommendations + one-click download
import { DownloadPanel } from './DownloadPanel'

type LocalModel = {
  name: string
  path: string
  launcher_model_ref?: string | null
  runtime?: string | null
  runnable?: boolean | null
  activation_supported?: boolean | null
  is_launch_default?: boolean | null
  is_live_active?: boolean | null
  activation_mode?: string | null
  activation_detail?: string | null
  runtime_status?: string | null
  runtime_note?: string | null
  setup_href?: string | null
  setup_label?: string | null
  architecture: string | null
  context_length: number | null
  quant: string | null
  parameter_count_b: number | null
  file_size_bytes: number
}

type InventoryResponse = {
  model_dir: string
  available: boolean
  launcher_config?: {
    available: boolean
    path: string
    provider: string
    default_model: string
    model_dir: string
    model_dir_matches_inventory: boolean
    active_gguf_model?: string
  }
  models: LocalModel[]
}

type RoleRoute = {
  role: string
  label: string
  confidence: number
  reason: string
  model: LocalModel | null
  manifest_alignment?: {
    status: 'primary' | 'curated' | 'untracked' | 'missing_model' | 'no_manifest' | string
    label: string
    reason: string
    matched_count: number
    primary_count: number
  }
  manifest_alternatives?: Array<ManifestAlternative>
  manifest_alternative_note?: string | null
  manifest_matches?: Array<{
    category: string
    role: string
    repo: string
    runtime_type: string
    estimated_status: string
  }>
}

type ManifestAlternative = ManifestModelEntry & {
  matched_model_name?: string | null
  matched_model_path?: string | null
  matched_model_runtime?: string | null
  reason: string
}

type ManifestSetupTask = {
  action_type: 'download_gguf' | 'download_snapshot' | 'configure_runtime' | 'manual' | string
  label: string
  description: string
  repo_id?: string | null
  filename?: string | null
  target_path?: string | null
  command?: string | null
  setup_href?: string | null
}

type ManifestModelEntry = {
  category: string
  role: string
  repo: string
  local_path?: string
  runtime_type: string
  estimated_status: string
  notes?: string
  status?: ManifestFilter
  status_reason?: string
  matched_model_name?: string | null
  matched_model_path?: string | null
  matched_model_runtime?: string | null
  setup_task?: ManifestSetupTask | null
}

type RoleRoutingResponse = {
  model_dir: string
  available: boolean
  manifest?: {
    path: string
    available: boolean
    entry_count: number
    matched_route_count: number
    alignment_counts?: {
      primary: number
      curated: number
      untracked: number
      missing_model: number
      no_manifest: number
    }
    unmatched_entry_count?: number
    unmatched_entries?: ManifestModelEntry[]
    reconciliation_counts?: {
      matched: number
      missing: number
      unsupported_runtime: number
    }
    reconciliation_entries?: ManifestModelEntry[]
  }
  routes: RoleRoute[]
}

type BenchmarkResult = {
  role: string
  label: string
  status: 'completed' | 'failed' | 'skipped'
  model_name?: string | null
  model_runtime?: string | null
  model_id?: string | null
  provider?: string | null
  latency_ms?: number | null
  tokens_per_second?: number | null
  score: number
  error?: string | null
}

type BenchmarkJob = {
  job_id: string
  roles: string[]
  status: 'queued' | 'running' | 'completed' | 'failed'
  results: BenchmarkResult[]
  error?: string | null
  created_at?: number | null
  completed_at?: number | null
}

type BenchmarkListResponse = {
  benchmarks: BenchmarkJob[]
}

type LaunchDefaultResponse = {
  ok: boolean
  detail: string
  launcher_config?: InventoryResponse['launcher_config']
}

type RevealPathResponse = {
  ok: boolean
  path: string
  detail: string
}

type ManifestRowApplyResponse = {
  ok: boolean
  manifest_path: string
  backup_path?: string | null
  row: string
  duplicate: boolean
  detail: string
  entry: ManifestModelEntry
}

type StartDownloadResponse = {
  job_id: string
  status: string
  target_path: string
  bytes_downloaded: number
  bytes_total: number
}

type SnapshotInstallJob = {
  job_id: string
  repo_id: string
  target_path: string
  status: 'queued' | 'downloading' | 'completed' | 'failed' | 'cancelled'
  error?: string | null
  log_tail: string[]
}

type SnapshotInstallListResponse = {
  snapshot_installs: SnapshotInstallJob[]
}

type SnapshotInstallCancelResponse = {
  ok: boolean
  detail: string
}

type InventoryFilter = 'all' | 'ready' | 'setup'
type ManifestFilter = 'all' | 'matched' | 'missing' | 'unsupported_runtime'
type InventorySort =
  | 'name-asc'
  | 'runtime-asc'
  | 'size-desc'
  | 'size-asc'
  | 'context-desc'
  | 'params-desc'

function fmtBytes(n: number): string {
  if (!n) return '—'
  const gb = n / (1024 * 1024 * 1024)
  if (gb >= 1) return `${gb.toFixed(2)} GB`
  const mb = n / (1024 * 1024)
  return `${mb.toFixed(0)} MB`
}

function fmtNCtx(n: number | null): string {
  if (!n) return '—'
  if (n >= 1024) return `${Math.round(n / 1024)}k`
  return String(n)
}

function fmtParams(n: number | null): string {
  if (!n) return '—'
  return `${n}B`
}

function roleIcon(role: string) {
  if (role === 'source_synthesis') return <BookOpenCheck className="h-4 w-4" />
  if (role === 'coding_research') return <Code2 className="h-4 w-4" />
  if (role === 'study_fast') return <GraduationCap className="h-4 w-4" />
  if (role === 'embedding') return <Database className="h-4 w-4" />
  return <BrainCircuit className="h-4 w-4" />
}

function manifestCell(value: string | null | undefined): string {
  return (value || '').replace(/\|/g, '/').trim()
}

function manifestDraftRow(cells: {
  category: string
  role: string
  repo: string
  localPath: string
  runtimeType: string
  estimatedStatus: string
  notes: string
}): string {
  const values = [
    manifestCell(cells.category),
    manifestCell(cells.role),
    `\`${manifestCell(cells.repo)}\``,
    `\`${manifestCell(cells.localPath)}\``,
    manifestCell(cells.runtimeType),
    manifestCell(cells.estimatedStatus),
    manifestCell(cells.notes),
  ]
  return `| ${values.join(' | ')} |`
}

function manifestDraftRowForAlternative(route: RoleRoute, alternative: ManifestAlternative): string {
  return manifestDraftRow({
    category: `${route.label} - Suggested`,
    role: `candidate - ${route.role}`,
    repo: alternative.repo,
    localPath: alternative.local_path || alternative.matched_model_path || '',
    runtimeType: alternative.runtime_type,
    estimatedStatus: 'suggested - review',
    notes: (
      `Open Notebook Plus suggested this curated ${alternative.role} manifest row `
      + `for ${route.label}; original category: ${alternative.category}.`
    ),
  })
}

function manifestDraftRowForRouteModel(route: RoleRoute): string | null {
  if (!route.model) return null
  return manifestDraftRow({
    category: `${route.label} - Suggested`,
    role: `candidate - ${route.role}`,
    repo: route.model.name,
    localPath: route.model.path,
    runtimeType: route.model.runtime || 'unknown',
    estimatedStatus: 'suggested - review',
    notes: (
      `Open Notebook Plus currently recommends this local model for ${route.label}, `
      + 'but it is not represented in the curated manifest yet.'
    ),
  })
}

function isRunnableLocalModel(model: LocalModel): boolean {
  if (typeof model.runnable === 'boolean') return model.runnable
  return !model.runtime || model.runtime === 'gguf' || model.runtime === 'mlx'
}

function supportsChatActivation(model: LocalModel): boolean {
  if (typeof model.activation_supported === 'boolean') return model.activation_supported
  return !model.runtime || model.runtime === 'gguf'
}

function supportsLaunchDefault(model: LocalModel): boolean {
  return (!model.runtime || model.runtime === 'gguf' || model.runtime === 'mlx')
    && Boolean(model.launcher_model_ref)
}

function launchDefaultButtonLabel(model: LocalModel, t: TFunction): string {
  if (model.is_launch_default) {
    return t('localModels.launchDefaultCurrent', {
      defaultValue: 'Launch default',
    })
  }
  if (model.runtime === 'mlx') {
    return t('localModels.useOnNextLaunch', {
      defaultValue: 'Use on next launch',
    })
  }
  return t('localModels.setLaunchDefault', {
    defaultValue: 'Set launch default',
  })
}

function matchesInventorySearch(model: LocalModel, query: string): boolean {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true
  return [
    model.name,
    model.path,
    model.launcher_model_ref,
    model.runtime,
    model.runtime_status,
    model.runtime_note,
    model.architecture,
    model.quant,
    model.parameter_count_b ? `${model.parameter_count_b}b` : null,
    model.context_length ? `${model.context_length}` : null,
  ]
    .filter(Boolean)
    .some(value => String(value).toLowerCase().includes(normalized))
}

function filterInventoryModels(
  models: LocalModel[],
  filter: InventoryFilter,
  searchQuery: string,
): LocalModel[] {
  const readinessFiltered = models.filter(model => {
    if (filter === 'ready') return isRunnableLocalModel(model)
    if (filter === 'setup') return !isRunnableLocalModel(model)
    return true
  })
  return readinessFiltered.filter(model => matchesInventorySearch(model, searchQuery))
}

function sortInventoryModels(models: LocalModel[], sort: InventorySort): LocalModel[] {
  const sorted = [...models]
  const byName = (left: LocalModel, right: LocalModel) =>
    left.name.localeCompare(right.name)
  const byNumberDesc = (
    left: LocalModel,
    right: LocalModel,
    pick: (model: LocalModel) => number | null,
  ) => (pick(right) ?? -1) - (pick(left) ?? -1) || byName(left, right)

  if (sort === 'runtime-asc') {
    return sorted.sort((left, right) =>
      (left.runtime || 'local').localeCompare(right.runtime || 'local') || byName(left, right),
    )
  }
  if (sort === 'size-desc') {
    return sorted.sort((left, right) =>
      byNumberDesc(left, right, model => model.file_size_bytes),
    )
  }
  if (sort === 'size-asc') {
    return sorted.sort((left, right) =>
      left.file_size_bytes - right.file_size_bytes || byName(left, right),
    )
  }
  if (sort === 'context-desc') {
    return sorted.sort((left, right) =>
      byNumberDesc(left, right, model => model.context_length),
    )
  }
  if (sort === 'params-desc') {
    return sorted.sort((left, right) =>
      byNumberDesc(left, right, model => model.parameter_count_b),
    )
  }
  return sorted.sort(byName)
}

function inventorySetupHref(model: LocalModel): string {
  return model.setup_href || '/settings/launcher-prefs'
}

function inventorySetupLabel(model: LocalModel, t: ReturnType<typeof useTranslation>['t']): string {
  return model.setup_label || t('localModels.openLauncherPrefs', {
    defaultValue: 'Open launcher preferences',
  })
}

function runtimeDisplayName(runtime: string | null | undefined): string {
  if (runtime === 'gguf') return 'GGUF'
  if (runtime === 'mlx') return 'MLX'
  if (runtime === 'transformers') return 'Transformers'
  return 'Local'
}

function manifestStatusLabel(status: ManifestFilter): string {
  if (status === 'matched') return 'Matched'
  if (status === 'missing') return 'Missing'
  if (status === 'unsupported_runtime') return 'Unsupported'
  return 'All'
}

function manifestStatusBadgeVariant(status?: ManifestFilter): 'outline' | 'secondary' | 'destructive' {
  if (status === 'matched') return 'secondary'
  if (status === 'missing') return 'destructive'
  return 'outline'
}

function healthStatusLabel(status: string): string {
  return status.replace(/_/g, ' ')
}

function healthStatusBadgeVariant(status: string): 'outline' | 'secondary' | 'destructive' {
  if (status === 'healthy') return 'secondary'
  if (status === 'unhealthy') return 'destructive'
  return 'outline'
}

function fleetSummary(models: LocalModel[]) {
  const runtimeCounts = models.reduce<Record<string, number>>((counts, model) => {
    const key = model.runtime || 'local'
    counts[key] = (counts[key] ?? 0) + 1
    return counts
  }, {})
  const totalBytes = models.reduce((total, model) => total + model.file_size_bytes, 0)
  const runnable = models.filter(isRunnableLocalModel).length
  return {
    total: models.length,
    runnable,
    inventoryOnly: models.length - runnable,
    runtimeCounts,
    totalBytes,
  }
}

function modelDisplayRef(model: LocalModel | null | undefined): string | null {
  if (!model) return null
  return model.launcher_model_ref || model.name || model.path || null
}

function findLaunchDefaultModel(
  models: LocalModel[],
  launcherDefault?: string | null,
): LocalModel | null {
  return models.find(model => model.is_launch_default)
    ?? models.find(model => Boolean(
      launcherDefault
      && (
        model.launcher_model_ref === launcherDefault
        || model.path === launcherDefault
        || model.name === launcherDefault
      ),
    ))
    ?? null
}

function isActiveJobStatus(status: string): boolean {
  return status === 'queued' || status === 'downloading' || status === 'running'
}

const LOCAL_DEFAULT_SLOTS: Array<{
  key: keyof ModelDefaults
  label: string
  hint: string
}> = [
  {
    key: 'default_chat_model',
    label: 'Chat',
    hint: 'General Q&A and source chat',
  },
  {
    key: 'default_transformation_model',
    label: 'Source synthesis',
    hint: 'Study guides, summaries, and Course Packs',
  },
  {
    key: 'default_tools_model',
    label: 'Coding / tools',
    hint: 'Tool use, code, and structured actions',
  },
  {
    key: 'large_context_model',
    label: 'Large context',
    hint: 'Long PDFs, transcripts, and notebooks',
  },
  {
    key: 'default_reasoning_model',
    label: 'Reasoning',
    hint: 'Slow, deeper analysis jobs',
  },
  {
    key: 'default_embedding_model',
    label: 'Embedding',
    hint: 'Retrieval and search memory',
  },
]

function modelNameById(models: Model[], id?: string | null): string | null {
  if (!id) return null
  return models.find(model => model.id === id)?.name ?? id
}

export default function LocalModelsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const localModelsHealth = useLocalModelsHealth()
  const registeredModels = useModels()
  const modelDefaults = useModelDefaults()
  const autoAssignCapability = useAutoAssignCapability()
  const [inventoryFilter, setInventoryFilter] = React.useState<InventoryFilter>('all')
  const [manifestFilter, setManifestFilter] = React.useState<ManifestFilter>('all')
  const [inventorySearch, setInventorySearch] = React.useState('')
  const [inventorySort, setInventorySort] = React.useState<InventorySort>('name-asc')
  const clearInventoryFilters = React.useCallback(() => {
    setInventoryFilter('all')
    setInventorySearch('')
    setInventorySort('name-asc')
  }, [])
  const copyText = React.useCallback(async (
    value: string,
    successMessage: string,
    failedMessage: string,
  ) => {
    try {
      await navigator.clipboard.writeText(value)
      toast.success(successMessage)
    } catch {
      toast.error(failedMessage)
    }
  }, [])
  const copyModelPath = React.useCallback(async (model: LocalModel) => {
    await copyText(
      model.path,
      t('localModels.copyPathSuccess', {
        defaultValue: 'Model path copied',
      }),
      t('localModels.copyPathFailed', {
        defaultValue: 'Could not copy model path',
      }),
    )
  }, [copyText, t])
  const copyManifestLocalPath = React.useCallback(async (entry: ManifestModelEntry) => {
    if (!entry.local_path) return
    await copyText(
      entry.local_path,
      t('localModels.copyManifestLocalPathSuccess', {
        defaultValue: 'Manifest local path copied',
      }),
      t('localModels.copyManifestLocalPathFailed', {
        defaultValue: 'Could not copy manifest local path',
      }),
    )
  }, [copyText, t])
  const copyMatchedModelPath = React.useCallback(async (entry: ManifestModelEntry) => {
    if (!entry.matched_model_path) return
    await copyText(
      entry.matched_model_path,
      t('localModels.copyMatchedModelPathSuccess', {
        defaultValue: 'Matched model path copied',
      }),
      t('localModels.copyMatchedModelPathFailed', {
        defaultValue: 'Could not copy matched model path',
      }),
    )
  }, [copyText, t])
  const copyManifestSetupCommand = React.useCallback(async (entry: ManifestModelEntry) => {
    const command = entry.setup_task?.command
    if (!command) return
    await copyText(
      command,
      t('localModels.copyManifestSetupCommandSuccess', {
        defaultValue: 'Setup command copied',
      }),
      t('localModels.copyManifestSetupCommandFailed', {
        defaultValue: 'Could not copy setup command',
      }),
    )
  }, [copyText, t])
  const copyManifestAlternativeDraftRow = React.useCallback(async (
    route: RoleRoute,
    alternative: ManifestAlternative,
  ) => {
    await copyText(
      manifestDraftRowForAlternative(route, alternative),
      t('localModels.copyManifestDraftRowSuccess', {
        defaultValue: 'Manifest draft row copied',
      }),
      t('localModels.copyManifestDraftRowFailed', {
        defaultValue: 'Could not copy manifest draft row',
      }),
    )
  }, [copyText, t])
  const copyRouteModelManifestDraftRow = React.useCallback(async (route: RoleRoute) => {
    const row = manifestDraftRowForRouteModel(route)
    if (!row) return
    await copyText(
      row,
      t('localModels.copyManifestDraftRowSuccess', {
        defaultValue: 'Manifest draft row copied',
      }),
      t('localModels.copyManifestDraftRowFailed', {
        defaultValue: 'Could not copy manifest draft row',
      }),
    )
  }, [copyText, t])
  const applyManifestDraftRow = useMutation({
    mutationFn: async (row: string) => {
      const resp = await apiClient.post<ManifestRowApplyResponse>(
        '/local-models/manifest/rows/apply',
        { row },
      )
      return resp.data
    },
    onSuccess: result => {
      toast.success(
        t('localModels.applyManifestDraftRowSuccess', {
          defaultValue: result.backup_path
            ? 'Manifest row applied. Backup created.'
            : 'Manifest row applied.',
        }),
      )
      queryClient.invalidateQueries({ queryKey: ['local-models', 'role-routing'] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast.error(
        t('localModels.applyManifestDraftRowFailed', {
          defaultValue: 'Could not apply manifest row: {{detail}}',
          detail: msg,
        }),
      )
    },
  })
  const applyManifestAlternativeDraftRow = React.useCallback((
    route: RoleRoute,
    alternative: ManifestAlternative,
  ) => {
    applyManifestDraftRow.mutate(manifestDraftRowForAlternative(route, alternative))
  }, [applyManifestDraftRow])
  const applyRouteModelManifestDraftRow = React.useCallback((route: RoleRoute) => {
    const row = manifestDraftRowForRouteModel(route)
    if (!row) return
    applyManifestDraftRow.mutate(row)
  }, [applyManifestDraftRow])
  const copyLauncherModelRef = React.useCallback(async (model: LocalModel) => {
    if (!model.launcher_model_ref) return
    await copyText(
      model.launcher_model_ref,
      t('localModels.copyLauncherRefSuccess', {
        defaultValue: 'Launcher reference copied',
      }),
      t('localModels.copyLauncherRefFailed', {
        defaultValue: 'Could not copy launcher reference',
      }),
    )
  }, [copyText, t])
  const { data, isLoading, isError, refetch } = useQuery<InventoryResponse>({
    queryKey: ['local-models', 'inventory'],
    queryFn: async () => {
      const resp = await apiClient.get<InventoryResponse>('/local-models/inventory')
      return resp.data
    },
    // Inventory is cheap — re-poll on focus so a user who drops a new
    // file in via Finder sees it without manual refresh.
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  })
  const hasRunnableModels = Boolean(data?.available && data.models.some(isRunnableLocalModel))
  const summary = data?.available ? fleetSummary(data.models) : null
  const inventoryModels = data?.models ?? []
  const filteredInventoryModels = sortInventoryModels(
    filterInventoryModels(inventoryModels, inventoryFilter, inventorySearch),
    inventorySort,
  )
  const roleRouting = useQuery<RoleRoutingResponse>({
    queryKey: ['local-models', 'role-routing'],
    queryFn: async () => {
      const resp = await apiClient.get<RoleRoutingResponse>('/local-models/role-routing')
      return resp.data
    },
    enabled: hasRunnableModels,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  })
  const roleRoutes = roleRouting.data?.routes ?? []
  const unmatchedManifestCount = roleRouting.data?.manifest?.unmatched_entry_count ?? 0
  const manifestReconciliationEntries = roleRouting.data?.manifest?.reconciliation_entries ?? []
  const manifestReconciliationCounts = roleRouting.data?.manifest?.reconciliation_counts ?? {
    matched: 0,
    missing: 0,
    unsupported_runtime: 0,
  }
  const filteredManifestReconciliationEntries = manifestFilter === 'all'
    ? manifestReconciliationEntries
    : manifestReconciliationEntries.filter(entry => entry.status === manifestFilter)
  const displayedManifestReconciliationEntries = filteredManifestReconciliationEntries.slice(0, 8)
  const snapshotInstalls = useQuery<SnapshotInstallListResponse>({
    queryKey: ['local-models', 'snapshot-installs'],
    queryFn: async () => {
      const resp = await apiClient.get<SnapshotInstallListResponse>(
        '/local-models/snapshot-installs',
      )
      return resp.data
    },
    enabled: Boolean(data?.available),
    refetchInterval: query => {
      const jobs = query.state.data?.snapshot_installs ?? []
      return jobs.some(job => job.status === 'queued' || job.status === 'downloading')
        ? 1500
        : false
    },
  })
  const benchmarks = useQuery<BenchmarkListResponse>({
    queryKey: ['local-models', 'benchmarks'],
    queryFn: async () => {
      const resp = await apiClient.get<BenchmarkListResponse>('/local-models/benchmarks')
      return resp.data
    },
    enabled: hasRunnableModels,
    refetchInterval: query => {
      const jobs = query.state.data?.benchmarks ?? []
      return jobs.some(job => job.status === 'queued' || job.status === 'running')
        ? 1500
        : false
    },
  })
  const startBenchmark = useMutation({
    mutationFn: async () => {
      const resp = await apiClient.post<BenchmarkJob>('/local-models/benchmarks', {
        roles: ['chat', 'source_synthesis', 'coding_research', 'study_fast'],
      })
      return resp.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['local-models', 'benchmarks'] })
    },
  })
  const latestBenchmark = startBenchmark.data ?? benchmarks.data?.benchmarks?.[0]
  const activeModel = inventoryModels.find(model => model.is_live_active) ?? null
  const launchDefaultModel = findLaunchDefaultModel(
    inventoryModels,
    data?.launcher_config?.default_model,
  )
  const activeModelRef = modelDisplayRef(activeModel) ?? data?.launcher_config?.active_gguf_model ?? null
  const launchDefaultModelRef = modelDisplayRef(launchDefaultModel)
    ?? data?.launcher_config?.default_model
    ?? null
  const launchDefaultDiffers = Boolean(
    activeModelRef
    && launchDefaultModelRef
    && activeModelRef !== launchDefaultModelRef
  )
  const activeSnapshotInstallCount = (
    snapshotInstalls.data?.snapshot_installs ?? []
  ).filter(job => isActiveJobStatus(job.status)).length
  const manifestAlignmentCounts = roleRouting.data?.manifest?.alignment_counts
  const manifestControlLabel = roleRouting.data?.manifest?.available
    ? t('localModels.controlManifestReady', {
      defaultValue: '{{primary}} primary, {{untracked}} untracked',
      primary: manifestAlignmentCounts?.primary ?? 0,
      untracked: manifestAlignmentCounts?.untracked ?? 0,
    })
    : roleRouting.isError
      ? t('localModels.controlManifestUnavailable', {
        defaultValue: 'Manifest unavailable',
      })
      : t('localModels.controlManifestWaiting', {
        defaultValue: 'Waiting for role scan',
      })
  const jobControlLabel = t('localModels.controlJobsLabel', {
    defaultValue: '{{installs}} installs, benchmark {{benchmark}}',
    installs: activeSnapshotInstallCount,
    benchmark: latestBenchmark?.status ?? 'idle',
  })
  const registeredModelList = Array.isArray(registeredModels.data)
    ? registeredModels.data
    : []
  const defaults = modelDefaults.data
  const assignedDefaultCount = defaults
    ? LOCAL_DEFAULT_SLOTS.filter(slot => Boolean(defaults[slot.key])).length
    : 0
  const revealModelPath = useMutation({
    mutationFn: async (path: string) => {
      const resp = await apiClient.post<RevealPathResponse>(
        '/local-models/reveal',
        { path },
      )
      return resp.data
    },
    onSuccess: () => {
      toast.success(
        t('localModels.revealPathSuccess', {
          defaultValue: 'Opened in file manager',
        }),
      )
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast.error(
        t('localModels.revealPathFailed', {
          defaultValue: 'Could not reveal model path: {{detail}}',
          detail: msg,
        }),
      )
    },
  })
  const startManifestDownload = useMutation({
    mutationFn: async (task: ManifestSetupTask) => {
      if (!task.repo_id || !task.filename) {
        throw new Error('Missing repo or filename for manifest download')
      }
      const resp = await apiClient.post<StartDownloadResponse>(
        '/local-models/download',
        {
          repo_id: task.repo_id,
          filename: task.filename,
          target_path: task.target_path,
        },
      )
      return resp.data
    },
    onSuccess: () => {
      toast.success(
        t('localModels.manifestDownloadStarted', {
          defaultValue: 'Manifest download task started',
        }),
      )
      queryClient.invalidateQueries({ queryKey: ['local-models', 'downloads'] })
      queryClient.invalidateQueries({ queryKey: ['local-models', 'inventory'] })
      queryClient.invalidateQueries({ queryKey: ['local-models', 'role-routing'] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast.error(
        t('localModels.manifestDownloadFailed', {
          defaultValue: 'Could not start manifest download: {{detail}}',
          detail: msg,
        }),
      )
    },
  })
  const startSnapshotInstall = useMutation({
    mutationFn: async (task: ManifestSetupTask) => {
      if (!task.repo_id || !task.target_path) {
        throw new Error('Missing repo or target path for snapshot install')
      }
      const resp = await apiClient.post<SnapshotInstallJob>(
        '/local-models/snapshot-installs',
        { repo_id: task.repo_id, target_path: task.target_path },
      )
      return resp.data
    },
    onSuccess: () => {
      toast.success(
        t('localModels.snapshotInstallStarted', {
          defaultValue: 'Snapshot install started',
        }),
      )
      queryClient.invalidateQueries({ queryKey: ['local-models', 'snapshot-installs'] })
      queryClient.invalidateQueries({ queryKey: ['local-models', 'inventory'] })
      queryClient.invalidateQueries({ queryKey: ['local-models', 'role-routing'] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast.error(
        t('localModels.snapshotInstallFailed', {
          defaultValue: 'Could not start snapshot install: {{detail}}',
          detail: msg,
        }),
      )
    },
  })
  const cancelSnapshotInstall = useMutation({
    mutationFn: async (jobId: string) => {
      const resp = await apiClient.post<SnapshotInstallCancelResponse>(
        `/local-models/snapshot-installs/${jobId}/cancel`,
      )
      return resp.data
    },
    onSuccess: () => {
      toast.success(
        t('localModels.snapshotInstallCancelRequested', {
          defaultValue: 'Snapshot install cancellation requested',
        }),
      )
      queryClient.invalidateQueries({ queryKey: ['local-models', 'snapshot-installs'] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast.error(
        t('localModels.snapshotInstallCancelFailed', {
          defaultValue: 'Could not cancel snapshot install: {{detail}}',
          detail: msg,
        }),
      )
    },
  })
  const [launchDefaultRef, setLaunchDefaultRef] = React.useState<string | null>(null)
  const setLaunchDefault = useMutation({
    mutationFn: async (model: LocalModel) => {
      const launcherRef = model.launcher_model_ref
      if (!launcherRef) {
        throw new Error('Missing launcher model reference')
      }
      setLaunchDefaultRef(launcherRef)
      try {
        const resp = await apiClient.post<LaunchDefaultResponse>(
          '/local-models/launch-default',
          { launcher_model_ref: launcherRef },
        )
        return resp.data
      } finally {
        setLaunchDefaultRef(null)
      }
    },
    onSuccess: () => {
      toast.success(
        t('localModels.launchDefaultSaved', {
          defaultValue: 'Native launcher default saved. Restart Open Notebook Plus to apply it.',
        }),
      )
      queryClient.invalidateQueries({ queryKey: ['local-models', 'inventory'] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast.error(
        t('localModels.launchDefaultFailed', {
          defaultValue: 'Could not set launch default: {{detail}}',
          detail: msg,
        }),
      )
    },
  })

  // v0.8.40b — hot-swap chat GGUF via the launcher control plane.
  // Tracks the path currently being swapped (for button-state UX)
  // so the user sees which card is in-flight even if they click
  // multiple in quick succession.
  const [activatingPath, setActivatingPath] = React.useState<string | null>(null)
  const setActive = useMutation({
    mutationFn: async (path: string) => {
      setActivatingPath(path)
      try {
        const resp = await apiClient.post<{
          ok: boolean; path: string; detail: string
        }>('/local-models/set-active', { path })
        return resp.data
      } finally {
        setActivatingPath(null)
      }
    },
    onSuccess: res => {
      if (res.ok) {
        toast.success(
          t('localModels.setActiveSuccess', {
            defaultValue: 'Active chat model switched: {{detail}}',
            detail: res.detail,
          }),
        )
        // Health badges may flip red briefly while the new sidecar
        // mmaps the GGUF — invalidate so the polling picks up the
        // transition.
        queryClient.invalidateQueries({ queryKey: ['local-models', 'health'] })
        queryClient.invalidateQueries({ queryKey: ['local-models', 'inventory'] })
        queryClient.invalidateQueries({ queryKey: ['local-models', 'role-routing'] })
      } else {
        toast.error(
          t('localModels.setActiveFailed', {
            defaultValue: 'Could not switch chat model: {{detail}}',
            detail: res.detail,
          }),
        )
      }
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      toast.error(
        t('localModels.setActiveFailed', {
          defaultValue: 'Could not switch chat model: {{detail}}',
          detail: msg,
        }),
      )
    },
  })

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="px-6 py-10 sm:px-8 space-y-8 max-w-4xl">
          {/* Header */}
          <header className="space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3">
              <Cpu className="h-7 w-7" />
              {t('localModels.title', { defaultValue: 'Local models' })}
            </h1>
            <p className="text-muted-foreground">
              {t('localModels.description', {
                defaultValue:
                  'GGUF files, MLX repositories, and Transformers repositories in your configured model directory. The smart router can pick from runnable local providers when chatting; drop new files in to add them.',
              })}
            </p>
          </header>

          {/* Refresh control */}
          <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 text-xs text-muted-foreground">
              {data && (
                <span className="flex min-w-0 items-center gap-1.5">
                  <FolderOpen className="h-3 w-3 shrink-0" />
                  <code className="min-w-0 break-all rounded bg-muted px-1.5 py-0.5">{data.model_dir || '—'}</code>
                </span>
              )}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => refetch()}
              disabled={isLoading}
              className="gap-1"
            >
              <RefreshCw className={`h-3 w-3 ${isLoading ? 'animate-spin' : ''}`} />
              {t('common.refresh', { defaultValue: 'Refresh' })}
            </Button>
          </div>

          {/* Error state */}
          {isError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>
                {t('localModels.errorTitle', { defaultValue: 'Could not load inventory' })}
              </AlertTitle>
              <AlertDescription>
                {t('localModels.errorDesc', {
                  defaultValue: 'The API returned an error. Check the API logs and try again.',
                })}
              </AlertDescription>
            </Alert>
          )}

          {/* Empty / unavailable states */}
          {data && !data.available && (
            <Alert>
              <FolderOpen className="h-4 w-4" />
              <AlertTitle>
                {t('localModels.dirMissingTitle', {
                  defaultValue: 'Model directory not found',
                })}
              </AlertTitle>
              <AlertDescription>
                {t('localModels.dirMissingDesc', {
                  defaultValue:
                    'The configured directory does not exist. Create it and drop .gguf files in, then refresh.',
                })}
                {data.model_dir && (
                  <>
                    {' '}
                    <code className="bg-muted px-1 py-0.5 rounded">{data.model_dir}</code>
                  </>
                )}
              </AlertDescription>
            </Alert>
          )}

          {data && data.available && data.models.length === 0 && (
            <Alert>
              <Sparkles className="h-4 w-4" />
              <AlertTitle>
                {t('localModels.emptyTitle', {
                  defaultValue: 'No models installed yet',
                })}
              </AlertTitle>
              <AlertDescription>
                {t('localModels.emptyDesc', {
                  defaultValue:
                    'Drop a .gguf file, complete MLX repository, or complete Transformers repository into the directory above, then click Refresh. We recommend Qwen2.5-7B-Instruct-Q4_K_M from HuggingFace as a starting point.',
                })}
                {' '}
                <Link
                  href="https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline"
                >
                  {t('localModels.emptyLink', { defaultValue: 'Browse on HuggingFace →' })}
                </Link>
              </AlertDescription>
            </Alert>
          )}

          {/* v0.8.39b — Recommendations + downloader.
              Shown whenever the model dir is reachable (even when
              empty — that's actually the most useful place for it:
              brand-new install, nothing installed yet, here are some
              good first picks). Hidden on dir-missing/error states
              since downloads need a real dest dir. */}
          {data && data.available && <DownloadPanel />}

          {data && data.available && (
            <Card data-testid="local-model-control-state">
              <CardHeader className="pb-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <Settings2 className="h-4 w-4 text-primary" />
                      {t('localModels.controlStateTitle', {
                        defaultValue: 'Control state',
                      })}
                    </CardTitle>
                    <CardDescription>
                      {t('localModels.controlStateDesc', {
                        defaultValue:
                          'Current runtime, next launch default, manifest alignment, and active local jobs.',
                      })}
                    </CardDescription>
                  </div>
                  {launchDefaultDiffers && (
                    <Badge variant="outline" className="w-fit text-xs">
                      {t('localModels.controlRestartNeeded', {
                        defaultValue: 'Restart applies next-launch default',
                      })}
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-md border bg-muted/20 px-3 py-3">
                    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                      <Power className="h-3.5 w-3.5" />
                      {t('localModels.controlActiveNowLabel', {
                        defaultValue: 'Active now',
                      })}
                    </div>
                    <div
                      className="mt-2 min-h-5 break-all font-mono text-sm"
                      data-testid="control-state-active-now"
                    >
                      {activeModelRef || t('localModels.controlNoActiveModel', {
                        defaultValue: 'No live GGUF detected',
                      })}
                    </div>
                    {activeModel?.runtime && (
                      <div className="mt-2">
                        <ModelFleetBadge runtime={activeModel.runtime} />
                      </div>
                    )}
                  </div>

                  <div className="rounded-md border bg-muted/20 px-3 py-3">
                    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                      <RefreshCw className="h-3.5 w-3.5" />
                      {t('localModels.controlLaunchDefaultLabel', {
                        defaultValue: 'Launch default',
                      })}
                    </div>
                    <div
                      className="mt-2 min-h-5 break-all font-mono text-sm"
                      data-testid="control-state-launch-default"
                    >
                      {launchDefaultModelRef || t('localModels.controlLaunchDefaultAuto', {
                        defaultValue: 'auto',
                      })}
                    </div>
                    {launchDefaultModel?.runtime && (
                      <div className="mt-2">
                        <ModelFleetBadge runtime={launchDefaultModel.runtime} />
                      </div>
                    )}
                  </div>

                  <div className="rounded-md border bg-muted/20 px-3 py-3">
                    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                      <Database className="h-3.5 w-3.5" />
                      {t('localModels.controlManifestLabel', {
                        defaultValue: 'Manifest',
                      })}
                    </div>
                    <div
                      className="mt-2 min-h-5 text-sm"
                      data-testid="control-state-manifest"
                    >
                      {manifestControlLabel}
                    </div>
                    {roleRouting.data?.manifest?.reconciliation_counts && (
                      <div className="mt-2 text-xs text-muted-foreground">
                        {t('localModels.controlManifestReconciliation', {
                          defaultValue: '{{matched}} matched, {{missing}} missing',
                          matched: roleRouting.data.manifest.reconciliation_counts.matched,
                          missing: roleRouting.data.manifest.reconciliation_counts.missing,
                        })}
                      </div>
                    )}
                  </div>

                  <div className="rounded-md border bg-muted/20 px-3 py-3">
                    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                      <Gauge className="h-3.5 w-3.5" />
                      {t('localModels.controlJobsTitle', {
                        defaultValue: 'Jobs',
                      })}
                    </div>
                    <div
                      className="mt-2 min-h-5 text-sm"
                      data-testid="control-state-jobs"
                    >
                      {jobControlLabel}
                    </div>
                    {latestBenchmark?.job_id && (
                      <div className="mt-2 truncate font-mono text-xs text-muted-foreground">
                        {latestBenchmark.job_id}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {data && data.available && hasRunnableModels && roleRouting.isError && (
            <Alert variant="destructive" data-testid="local-model-role-routing-error">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>
                {t('localModels.roleRoutingErrorTitle', {
                  defaultValue: 'Role routing unavailable',
                })}
              </AlertTitle>
              <AlertDescription>
                {t('localModels.roleRoutingErrorDesc', {
                  defaultValue:
                    'The local router could not score installed models. Inventory controls still work, but recommendations and manifest alignment may be stale.',
                })}
              </AlertDescription>
            </Alert>
          )}

          {data && data.available && (
            <section className="space-y-4" data-testid="local-model-routing-defaults">
              <div className="space-y-1">
                <h2 className="text-xl font-semibold tracking-tight">
                  {t('localModels.routingDefaultsTitle', {
                    defaultValue: 'Local routing and defaults',
                  })}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {t('localModels.routingDefaultsDesc', {
                    defaultValue:
                      'Control whether Open Notebook Plus uses local, cloud, or automatic routing, then fill app defaults from your registered model fleet.',
                  })}
                </p>
              </div>

              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.9fr)]">
                {defaults ? (
                  <SmartRoutingPanel defaults={defaults} />
                ) : (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">
                        {t('models.smartRouting.title', {
                          defaultValue: 'Smart routing',
                        })}
                      </CardTitle>
                      <CardDescription>
                        {modelDefaults.isError
                          ? t('localModels.defaultsErrorDesc', {
                            defaultValue: 'Could not load routing defaults.',
                          })
                          : t('localModels.defaultsLoadingDesc', {
                            defaultValue: 'Loading routing defaults.',
                          })}
                      </CardDescription>
                    </CardHeader>
                  </Card>
                )}

                <Card data-testid="local-model-defaults-preview">
                  <CardHeader className="pb-3">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <CardTitle className="text-base font-medium flex items-center gap-2">
                          <BrainCircuit className="h-4 w-4 text-primary" />
                          {t('localModels.defaultsPreviewTitle', {
                            defaultValue: 'App defaults',
                          })}
                        </CardTitle>
                        <CardDescription>
                          {t('localModels.defaultsPreviewDesc', {
                            defaultValue:
                              'The registered models Open Notebook Plus will use for chat, synthesis, tools, long context, reasoning, and retrieval.',
                          })}
                        </CardDescription>
                      </div>
                      {defaults && (
                        <Badge variant="outline" className="w-fit text-xs">
                          {t('localModels.defaultsAssignedCount', {
                            defaultValue: '{{count}} / {{total}} assigned',
                            count: assignedDefaultCount,
                            total: LOCAL_DEFAULT_SLOTS.length,
                          })}
                        </Badge>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid gap-2">
                      {LOCAL_DEFAULT_SLOTS.map(slot => {
                        const assigned = defaults
                          ? modelNameById(registeredModelList, defaults[slot.key] as string | null | undefined)
                          : null
                        return (
                          <div
                            key={slot.key}
                            className="rounded-md border bg-muted/20 px-3 py-2"
                            data-testid={`local-model-default-${slot.key}`}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <div className="text-sm font-medium">{slot.label}</div>
                                <div className="mt-0.5 text-xs text-muted-foreground">
                                  {slot.hint}
                                </div>
                              </div>
                              <Badge
                                variant={assigned ? 'secondary' : 'outline'}
                                className="shrink-0 text-[0.68rem]"
                              >
                                {assigned
                                  ? t('localModels.defaultAssigned', {
                                    defaultValue: 'Assigned',
                                  })
                                  : t('localModels.defaultEmpty', {
                                    defaultValue: 'Empty',
                                  })}
                              </Badge>
                            </div>
                            <div className="mt-2 break-all font-mono text-xs text-muted-foreground">
                              {assigned || t('localModels.defaultNotSet', {
                                defaultValue: 'Not set',
                              })}
                            </div>
                          </div>
                        )
                      })}
                    </div>

                    <div className="flex flex-col gap-2 sm:flex-row">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="gap-1.5"
                        disabled={autoAssignCapability.isPending}
                        onClick={() => autoAssignCapability.mutate({ force: false })}
                      >
                        {autoAssignCapability.isPending ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Sparkles className="h-3 w-3" />
                        )}
                        {t('localModels.fillEmptyDefaults', {
                          defaultValue: 'Fill empty slots',
                        })}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="gap-1.5"
                        disabled={autoAssignCapability.isPending}
                        onClick={() => autoAssignCapability.mutate({ force: true })}
                      >
                        {autoAssignCapability.isPending ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <RefreshCw className="h-3 w-3" />
                        )}
                        {t('localModels.resetDefaults', {
                          defaultValue: 'Reset and re-evaluate',
                        })}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </section>
          )}

          {data && data.available && localModelsHealth.data && (
            <Card data-testid="local-model-connection-checks">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <Gauge className="h-4 w-4 text-primary" />
                      {t('localModels.connectionChecksTitle', {
                        defaultValue: 'Connection checks',
                      })}
                    </CardTitle>
                    <CardDescription>
                      {t('localModels.connectionChecksDesc', {
                        defaultValue:
                          'Reachability for registered local endpoints and sidecars.',
                      })}
                    </CardDescription>
                  </div>
                  <Badge variant="outline" className="text-xs">
                    {localModelsHealth.data.overall}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="grid gap-2 sm:grid-cols-2">
                {localModelsHealth.data.models.map(model => (
                  <div
                    key={model.name}
                    className="rounded-md border bg-muted/20 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">
                          {model.name}
                        </div>
                        {(model.runtime || model.endpoint) && (
                          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.68rem] text-muted-foreground">
                            {model.runtime && (
                              <span className="font-medium uppercase tracking-wide">
                                {model.runtime}
                              </span>
                            )}
                            {model.endpoint && (
                              <span className="truncate">
                                {model.endpoint}
                                {model.probe_path ? model.probe_path : ''}
                              </span>
                            )}
                          </div>
                        )}
                        <div className="mt-1 truncate text-xs text-muted-foreground">
                          {model.detail || t('models.status.noDetail', {
                            defaultValue: 'No detail',
                          })}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <Badge
                          variant={healthStatusBadgeVariant(model.status)}
                          className="text-[0.68rem]"
                        >
                          {healthStatusLabel(model.status)}
                        </Badge>
                        {model.latency_ms != null && (
                          <div className="mt-1 text-[0.68rem] text-muted-foreground">
                            {model.latency_ms} ms
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {data && data.available && data.launcher_config?.available && (
            <Card data-testid="local-model-launcher-config">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium flex items-center gap-2">
                  <Power className="h-4 w-4 text-primary" />
                  {t('localModels.launcherConfigTitle', {
                    defaultValue: 'Native launcher',
                  })}
                </CardTitle>
                <CardDescription>
                  {t('localModels.launcherConfigDesc', {
                    defaultValue:
                      'Current desktop provider and default model from the native app config.',
                  })}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <dl className="grid gap-3 text-xs sm:grid-cols-3">
                  <div>
                    <dt className="text-muted-foreground">
                      {t('localModels.launcherProviderLabel', {
                        defaultValue: 'Provider',
                      })}
                    </dt>
                    <dd className="mt-1 font-mono">
                      {data.launcher_config.provider || 'none'}
                    </dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="text-muted-foreground">
                      {t('localModels.launcherDefaultModelLabel', {
                        defaultValue: 'Default model',
                      })}
                    </dt>
                    <dd className="mt-1 break-all font-mono">
                      {data.launcher_config.default_model || 'auto'}
                    </dd>
                  </div>
                </dl>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant={
                      data.launcher_config.model_dir_matches_inventory
                        ? 'secondary'
                        : 'destructive'
                    }
                    className="text-xs"
                  >
                    {data.launcher_config.model_dir_matches_inventory
                      ? t('localModels.launcherDirMatches', {
                        defaultValue: 'Model directory matches inventory',
                      })
                      : t('localModels.launcherDirMismatch', {
                        defaultValue: 'Model directory differs from inventory',
                      })}
                  </Badge>
                  <Button asChild variant="outline" size="sm" className="h-7 text-xs">
                    <Link href="/settings/launcher-prefs">
                      {t('localModels.openLauncherPrefs', {
                        defaultValue: 'Open launcher preferences',
                      })}
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {data && data.available && data.models.length > 0 && summary && (
            <Card data-testid="local-model-fleet-summary">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium flex items-center gap-2">
                  <Cpu className="h-4 w-4 text-primary" />
                  {t('localModels.fleetSummaryTitle', {
                    defaultValue: 'Model fleet',
                  })}
                </CardTitle>
                <CardDescription>
                  {t('localModels.fleetSummaryDesc', {
                    defaultValue:
                      'Runtime coverage and readiness for the models in this local directory.',
                  })}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-4">
                  <div
                    className="rounded-md border bg-muted/20 px-3 py-3"
                    data-testid="fleet-summary-installed"
                  >
                    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                      <Database className="h-3.5 w-3.5" />
                      {t('localModels.fleetInstalledLabel', {
                        defaultValue: 'Installed assets',
                      })}
                    </div>
                    <div className="mt-2 text-2xl font-semibold tabular-nums">
                      {summary.total}
                    </div>
                  </div>
                  <div
                    className="rounded-md border bg-muted/20 px-3 py-3"
                    data-testid="fleet-summary-runnable"
                  >
                    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                      <Gauge className="h-3.5 w-3.5" />
                      {t('localModels.fleetRunnableLabel', {
                        defaultValue: 'Ready to use',
                      })}
                    </div>
                    <div className="mt-2 text-2xl font-semibold tabular-nums">
                      {summary.runnable}
                    </div>
                  </div>
                  <div
                    className="rounded-md border bg-muted/20 px-3 py-3"
                    data-testid="fleet-summary-inventory-only"
                  >
                    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                      <AlertCircle className="h-3.5 w-3.5" />
                      {t('localModels.fleetSetupLabel', {
                        defaultValue: 'Setup needed',
                      })}
                    </div>
                    <div className="mt-2 text-2xl font-semibold tabular-nums">
                      {summary.inventoryOnly}
                    </div>
                  </div>
                  <div
                    className="rounded-md border bg-muted/20 px-3 py-3"
                    data-testid="fleet-summary-storage"
                  >
                    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                      <HardDrive className="h-3.5 w-3.5" />
                      {t('localModels.fleetStorageLabel', {
                        defaultValue: 'Storage',
                      })}
                    </div>
                    <div className="mt-2 text-2xl font-semibold tabular-nums">
                      {fmtBytes(summary.totalBytes)}
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline" className="text-xs" data-testid="fleet-total-count">
                    {summary.total} total
                  </Badge>
                  <Badge variant="outline" className="text-xs" data-testid="fleet-runnable-count">
                    {summary.runnable} runnable
                  </Badge>
                  <Badge
                    variant="outline"
                    className="text-xs"
                    data-testid="fleet-inventory-only-count"
                  >
                    {summary.inventoryOnly} inventory-only
                  </Badge>
                  {Object.entries(summary.runtimeCounts)
                    .sort(([left], [right]) => runtimeDisplayName(left).localeCompare(runtimeDisplayName(right)))
                    .map(([runtime, count]) => (
                      <Badge
                        key={runtime}
                        variant="secondary"
                        className="text-xs"
                        data-testid={`fleet-runtime-${runtime}`}
                      >
                        {count} {runtimeDisplayName(runtime)}
                      </Badge>
                    ))}
                </div>
              </CardContent>
            </Card>
          )}

          {data && data.available && manifestReconciliationEntries.length > 0 && (
            <Card data-testid="local-model-manifest-reconciliation">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-amber-600" />
                  {t('localModels.manifestReconciliationTitle', {
                    defaultValue: 'Manifest reconciliation',
                  })}
                </CardTitle>
                <CardDescription>
                  {t('localModels.manifestReconciliationDesc', {
                    defaultValue:
                      'Compare your curated AI_Models manifest against the current scan by matched, missing, and unsupported runtime rows.',
                  })}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <Tabs
                    value={manifestFilter}
                    onValueChange={value => setManifestFilter(value as ManifestFilter)}
                  >
                    <TabsList aria-label="Filter manifest reconciliation">
                      {(['all', 'matched', 'missing', 'unsupported_runtime'] as ManifestFilter[]).map(status => (
                        <TabsTrigger
                          key={status}
                          value={status}
                          onClick={() => setManifestFilter(status)}
                        >
                          {manifestStatusLabel(status)}
                          <Badge variant="secondary" className="ml-1 text-[0.68rem]">
                            {status === 'all'
                              ? manifestReconciliationEntries.length
                              : manifestReconciliationCounts[status] ?? 0}
                          </Badge>
                        </TabsTrigger>
                      ))}
                    </TabsList>
                  </Tabs>
                  <div className="flex flex-wrap gap-2">
                    {unmatchedManifestCount > 0 && (
                      <Badge variant="outline" className="text-xs">
                        {unmatchedManifestCount} unmatched
                      </Badge>
                    )}
                    {roleRouting.data?.manifest?.path && (
                      <Badge variant="secondary" className="max-w-full truncate text-xs">
                        {roleRouting.data.manifest.path}
                      </Badge>
                    )}
                  </div>
                </div>
                <div className="grid gap-2">
                  {displayedManifestReconciliationEntries.map(entry => (
                    <div
                      key={`${entry.status}-${entry.repo}-${entry.category}-${entry.role}`}
                      className="rounded-md border bg-muted/20 p-3 text-xs"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{entry.category}</span>
                          <Badge
                            variant={manifestStatusBadgeVariant(entry.status)}
                            className="text-[0.68rem]"
                          >
                            {manifestStatusLabel(entry.status || 'all')}
                          </Badge>
                          <Badge variant="outline" className="text-[0.68rem]">
                            {entry.role}
                          </Badge>
                          <Badge variant="secondary" className="text-[0.68rem]">
                            {entry.runtime_type}
                          </Badge>
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5">
                          {entry.local_path && (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-7 gap-1.5 px-2 text-xs"
                              onClick={() => copyManifestLocalPath(entry)}
                              aria-label={t('localModels.copyManifestLocalPathAria', {
                                defaultValue: 'Copy manifest local path for {{repo}}',
                                repo: entry.repo,
                              })}
                            >
                              <Copy className="h-3 w-3" />
                              {t('localModels.copyManifestLocalPath', {
                                defaultValue: 'Manifest path',
                              })}
                            </Button>
                          )}
                          {entry.matched_model_path && (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-7 gap-1.5 px-2 text-xs"
                              onClick={() => copyMatchedModelPath(entry)}
                              aria-label={t('localModels.copyMatchedModelPathAria', {
                                defaultValue: 'Copy matched scan path for {{repo}}',
                                repo: entry.repo,
                              })}
                            >
                              <Copy className="h-3 w-3" />
                              {t('localModels.copyMatchedModelPath', {
                                defaultValue: 'Scan path',
                              })}
                            </Button>
                          )}
                          {entry.matched_model_path && (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-7 gap-1.5 px-2 text-xs"
                              disabled={revealModelPath.isPending}
                              onClick={() => revealModelPath.mutate(entry.matched_model_path!)}
                              aria-label={t('localModels.revealMatchedModelPathAria', {
                                defaultValue: 'Reveal matched model path for {{repo}}',
                                repo: entry.repo,
                              })}
                            >
                              <FolderOpen className="h-3 w-3" />
                              {t('localModels.revealMatchedModelPath', {
                                defaultValue: 'Reveal',
                              })}
                            </Button>
                          )}
                          {entry.setup_task?.action_type === 'download_gguf'
                            && entry.setup_task.repo_id
                            && entry.setup_task.filename && (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-7 gap-1.5 px-2 text-xs"
                                disabled={startManifestDownload.isPending}
                                onClick={() => startManifestDownload.mutate(entry.setup_task!)}
                                aria-label={t('localModels.startManifestGgufDownloadAria', {
                                  defaultValue: 'Start GGUF download for {{repo}}',
                                  repo: entry.repo,
                                })}
                              >
                                <Download className="h-3 w-3" />
                                {t('localModels.startManifestGgufDownload', {
                                  defaultValue: 'Download',
                                })}
                              </Button>
                            )}
                          {entry.setup_task?.action_type === 'download_snapshot'
                            && entry.setup_task.command && (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-7 gap-1.5 px-2 text-xs"
                                onClick={() => copyManifestSetupCommand(entry)}
                                aria-label={t('localModels.copyManifestSetupCommandAria', {
                                  defaultValue: 'Copy setup command for {{repo}}',
                                  repo: entry.repo,
                                })}
                              >
                                <Copy className="h-3 w-3" />
                                {t('localModels.copyManifestSetupCommand', {
                                  defaultValue: 'Setup command',
                                })}
                              </Button>
                            )}
                          {entry.setup_task?.action_type === 'download_snapshot'
                            && entry.setup_task.repo_id
                            && entry.setup_task.target_path && (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-7 gap-1.5 px-2 text-xs"
                                disabled={startSnapshotInstall.isPending}
                                onClick={() => startSnapshotInstall.mutate(entry.setup_task!)}
                                aria-label={t('localModels.startSnapshotInstallAria', {
                                  defaultValue: 'Start snapshot install for {{repo}}',
                                  repo: entry.repo,
                                })}
                              >
                                <Download className="h-3 w-3" />
                                {t('localModels.startSnapshotInstall', {
                                  defaultValue: 'Install snapshot',
                                })}
                              </Button>
                            )}
                          {entry.status === 'unsupported_runtime' && (
                            <Button asChild variant="outline" size="sm" className="h-7 gap-1.5 px-2 text-xs">
                              <Link
                                href="/settings/launcher-prefs"
                                aria-label={t('localModels.openLauncherPrefsForManifestAria', {
                                  defaultValue: 'Open launcher preferences for {{repo}}',
                                  repo: entry.repo,
                                })}
                              >
                                <Settings2 className="h-3 w-3" />
                                {t('localModels.setupRuntime', {
                                  defaultValue: 'Setup',
                                })}
                              </Link>
                            </Button>
                          )}
                        </div>
                      </div>
                      <div className="mt-2 break-all font-mono text-muted-foreground">
                        {entry.repo}
                      </div>
                      {entry.local_path && (
                        <div className="mt-1 break-all font-mono text-[0.68rem] text-muted-foreground">
                          {entry.local_path}
                        </div>
                      )}
                      <div className="mt-1 text-muted-foreground">
                        {entry.status_reason || entry.estimated_status}
                      </div>
                      {entry.matched_model_name && (
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-muted-foreground">
                          <ModelFleetBadge runtime={entry.matched_model_runtime} />
                          <span className="break-all font-mono">
                            {entry.matched_model_name}
                          </span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                {filteredManifestReconciliationEntries.length === 0 && (
                  <div className="rounded-md border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">
                    {t('localModels.noManifestMatches', {
                      defaultValue: 'No manifest rows match this filter.',
                    })}
                  </div>
                )}
                {filteredManifestReconciliationEntries.length > displayedManifestReconciliationEntries.length && (
                  <p className="text-xs text-muted-foreground">
                    {t('localModels.manifestReconciliationMore', {
                      defaultValue: '{{count}} more rows are available through the API.',
                      count: filteredManifestReconciliationEntries.length - displayedManifestReconciliationEntries.length,
                    })}
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {data && data.available && (snapshotInstalls.data?.snapshot_installs?.length ?? 0) > 0 && (
            <Card data-testid="local-model-snapshot-installs">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium flex items-center gap-2">
                  <Download className="h-4 w-4 text-primary" />
                  {t('localModels.snapshotInstallsTitle', {
                    defaultValue: 'Snapshot installs',
                  })}
                </CardTitle>
                <CardDescription>
                  {t('localModels.snapshotInstallsDesc', {
                    defaultValue:
                      'Managed Hugging Face repo-folder installs for MLX, Transformers, and experimental model snapshots.',
                  })}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {(snapshotInstalls.data?.snapshot_installs ?? []).map(job => (
                  <div key={job.job_id} className="rounded-md border bg-muted/20 px-3 py-2 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="break-all font-medium">{job.repo_id}</div>
                        <div className="mt-1 break-all font-mono text-muted-foreground">
                          {job.target_path}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Badge
                          variant={job.status === 'failed' ? 'destructive' : 'outline'}
                          className="text-[0.68rem]"
                        >
                          {job.status}
                        </Badge>
                        {(job.status === 'queued' || job.status === 'downloading') && (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7 gap-1.5 px-2 text-xs"
                            disabled={cancelSnapshotInstall.isPending}
                            onClick={() => cancelSnapshotInstall.mutate(job.job_id)}
                            aria-label={t('localModels.cancelSnapshotInstallAria', {
                              defaultValue: 'Cancel snapshot install for {{repo}}',
                              repo: job.repo_id,
                            })}
                          >
                            <CircleStop className="h-3 w-3" />
                            {t('common.cancel', { defaultValue: 'Cancel' })}
                          </Button>
                        )}
                      </div>
                    </div>
                    {(job.error || job.log_tail?.length > 0) && (
                      <div className="mt-2 space-y-1 text-muted-foreground">
                        {job.error && (
                          <div className="text-destructive">{job.error}</div>
                        )}
                        {job.log_tail?.slice(-2).map((line, index) => (
                          <div
                            key={`${job.job_id}-log-${index}`}
                            className="break-all font-mono text-[0.68rem]"
                          >
                            {line}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {data && data.available && manifestReconciliationEntries.length === 0 && unmatchedManifestCount > 0 && (
            <Card data-testid="local-model-manifest-gaps">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-amber-600" />
                  {t('localModels.manifestGapsTitle', {
                    defaultValue: 'Curated manifest gaps',
                  })}
                </CardTitle>
                <CardDescription>
                  {t('localModels.manifestGapsDesc', {
                    defaultValue:
                      'These manifest rows did not match the current local scan. Check for moved folders, incomplete downloads, or unsupported runtime layouts.',
                  })}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline" className="text-xs">
                    {unmatchedManifestCount} unmatched
                  </Badge>
                  {roleRouting.data?.manifest?.path && (
                    <Badge variant="secondary" className="max-w-full truncate text-xs">
                      {roleRouting.data.manifest.path}
                    </Badge>
                  )}
                </div>
                <div className="grid gap-2">
                  {(roleRouting.data?.manifest?.unmatched_entries ?? []).slice(0, 5).map(entry => (
                    <div
                      key={`${entry.repo}-${entry.category}-${entry.role}`}
                      className="rounded-md border bg-muted/20 p-3 text-xs"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{entry.category}</span>
                        <Badge variant="outline" className="text-[0.68rem]">
                          {entry.role}
                        </Badge>
                        <Badge variant="secondary" className="text-[0.68rem]">
                          {entry.runtime_type}
                        </Badge>
                      </div>
                      <div className="mt-2 break-all font-mono text-muted-foreground">
                        {entry.repo}
                      </div>
                      {entry.estimated_status && (
                        <div className="mt-1 text-muted-foreground">
                          {entry.estimated_status}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                {unmatchedManifestCount > (roleRouting.data?.manifest?.unmatched_entries ?? []).slice(0, 5).length && (
                  <p className="text-xs text-muted-foreground">
                    {t('localModels.manifestGapsMore', {
                      defaultValue: '{{count}} more unmatched rows are available through the API.',
                      count: unmatchedManifestCount - (roleRouting.data?.manifest?.unmatched_entries ?? []).slice(0, 5).length,
                    })}
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {data && data.available && hasRunnableModels && roleRoutes.length > 0 && (
            <Card data-testid="local-model-role-routing">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-medium flex items-center gap-2">
                  <BrainCircuit className="h-4 w-4 text-primary" />
                  {t('localModels.roleRoutingTitle', {
                    defaultValue: 'Recommended local roles',
                  })}
                </CardTitle>
                <CardDescription>
                  {t('localModels.roleRoutingDesc', {
                    defaultValue:
                      'Open Notebook Plus scores your installed local fleet for the jobs it runs most often.',
                  })}
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-2 sm:grid-cols-2">
                {roleRoutes.map(route => (
                  <div
                    key={route.role}
                    className="rounded-md border bg-muted/20 p-3 min-w-0"
                    data-testid={`local-model-role-${route.role}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 space-y-1">
                        <div className="flex items-center gap-2 text-sm font-medium">
                          <span className="text-primary" aria-hidden="true">
                            {roleIcon(route.role)}
                          </span>
                          <span className="truncate">{route.label}</span>
                        </div>
                        <div className="text-xs text-muted-foreground line-clamp-2">
                          {route.reason}
                        </div>
                      </div>
                      <Badge variant="outline" className="shrink-0 text-xs">
                        {Math.round(route.confidence * 100)}%
                      </Badge>
                    </div>
                    <div className="mt-3 flex items-center gap-2 min-w-0">
                      {route.model ? (
                        <>
                          <ModelFleetBadge runtime={route.model.runtime} />
                          <span className="truncate text-xs font-mono">
                            {route.model.name}
                          </span>
                        </>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          {t('localModels.roleNoFit', {
                            defaultValue: 'No matching local model yet',
                          })}
                        </span>
                      )}
                    </div>
                    {route.manifest_alignment && (
                      <div
                        className="mt-3 space-y-1.5"
                        data-testid={`local-model-role-${route.role}-manifest-alignment`}
                      >
                        <Badge
                          variant={route.manifest_alignment.status === 'untracked' ? 'outline' : 'secondary'}
                          className="max-w-full truncate text-xs"
                        >
                          {route.manifest_alignment.label}
                        </Badge>
                        <div className="line-clamp-2 text-xs text-muted-foreground">
                          {route.manifest_alignment.reason}
                        </div>
                      </div>
                    )}
                    {route.manifest_matches && route.manifest_matches.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {route.manifest_matches.slice(0, 2).map(match => (
                          <Badge
                            key={`${route.role}-${match.repo}-${match.category}-${match.role}`}
                            variant="secondary"
                            className="max-w-full truncate text-xs"
                            data-testid={`local-model-role-${route.role}-manifest-match`}
                            title={`${match.category} / ${match.role}`}
                          >
                            Manifest: {match.category} · {match.role}
                          </Badge>
                        ))}
                      </div>
                    )}
                    {route.manifest_alternatives && route.manifest_alternatives.length > 0 && (
                      <div
                        className="mt-3 space-y-1.5 rounded-md border border-dashed bg-background/60 p-2"
                        data-testid={`local-model-role-${route.role}-manifest-alternatives`}
                      >
                        <div className="text-[0.68rem] font-medium uppercase tracking-wide text-muted-foreground">
                          {t('localModels.manifestAlternativesTitle', {
                            defaultValue: 'Curated alternatives',
                          })}
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {route.manifest_alternatives.slice(0, 2).map(alternative => (
                            <div
                              key={`${route.role}-alt-${alternative.repo}-${alternative.category}-${alternative.role}`}
                              className="flex min-w-0 flex-wrap items-center gap-1.5"
                            >
                              <Badge
                                variant="outline"
                                className="max-w-full truncate text-xs"
                                title={alternative.reason}
                              >
                                {alternative.category} · {alternative.role}
                              </Badge>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-7 gap-1.5 px-2 text-xs"
                                onClick={() => copyManifestAlternativeDraftRow(route, alternative)}
                                aria-label={t('localModels.copyAlternativeManifestDraftRowAria', {
                                  defaultValue: 'Copy manifest draft row for {{repo}}',
                                  repo: alternative.repo,
                                })}
                              >
                                <Copy className="h-3 w-3" />
                                {t('localModels.copyManifestDraftRow', {
                                  defaultValue: 'Copy row',
                                })}
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-7 gap-1.5 px-2 text-xs"
                                onClick={() => applyManifestAlternativeDraftRow(route, alternative)}
                                disabled={applyManifestDraftRow.isPending}
                                aria-label={t('localModels.applyAlternativeManifestDraftRowAria', {
                                  defaultValue: 'Apply manifest draft row for {{repo}}',
                                  repo: alternative.repo,
                                })}
                              >
                                {applyManifestDraftRow.isPending ? (
                                  <Loader2 className="h-3 w-3 animate-spin" />
                                ) : (
                                  <FilePlus className="h-3 w-3" />
                                )}
                                {t('localModels.applyManifestDraftRow', {
                                  defaultValue: 'Apply row',
                                })}
                              </Button>
                            </div>
                          ))}
                        </div>
                        <div className="line-clamp-2 text-xs text-muted-foreground">
                          {route.manifest_alternatives[0]?.reason}
                        </div>
                      </div>
                    )}
                    {route.manifest_alternative_note && (
                      <div
                        className="mt-3 space-y-2 rounded-md border border-dashed bg-background/60 p-2 text-xs text-muted-foreground"
                        data-testid={`local-model-role-${route.role}-manifest-alternative-note`}
                      >
                        <div>{route.manifest_alternative_note}</div>
                        {route.model && (
                          <>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-7 gap-1.5 px-2 text-xs"
                              onClick={() => copyRouteModelManifestDraftRow(route)}
                              aria-label={t('localModels.copyRouteModelManifestDraftRowAria', {
                                defaultValue: 'Copy manifest draft row for {{name}}',
                                name: route.model.name,
                              })}
                            >
                              <Copy className="h-3 w-3" />
                              {t('localModels.copyManifestDraftRow', {
                                defaultValue: 'Copy row',
                              })}
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-7 gap-1.5 px-2 text-xs"
                              onClick={() => applyRouteModelManifestDraftRow(route)}
                              disabled={applyManifestDraftRow.isPending}
                              aria-label={t('localModels.applyRouteModelManifestDraftRowAria', {
                                defaultValue: 'Apply manifest draft row for {{name}}',
                                name: route.model.name,
                              })}
                            >
                              {applyManifestDraftRow.isPending ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <FilePlus className="h-3 w-3" />
                              )}
                              {t('localModels.applyManifestDraftRow', {
                                defaultValue: 'Apply row',
                              })}
                            </Button>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {data && data.available && hasRunnableModels && (
            <Card data-testid="local-model-benchmarks">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle className="text-base font-medium flex items-center gap-2">
                      <Gauge className="h-4 w-4 text-primary" />
                      {t('localModels.benchmarkTitle', {
                        defaultValue: 'Local benchmark',
                      })}
                    </CardTitle>
                    <CardDescription>
                      {t('localModels.benchmarkDesc', {
                        defaultValue:
                          'Measure recommended registered models for chat, synthesis, coding, and study jobs.',
                      })}
                    </CardDescription>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={startBenchmark.isPending}
                    onClick={() => startBenchmark.mutate()}
                  >
                    {startBenchmark.isPending ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Gauge className="h-3 w-3" />
                    )}
                    {t('localModels.runBenchmark', {
                      defaultValue: 'Run local benchmark',
                    })}
                  </Button>
                </div>
              </CardHeader>
              {latestBenchmark && (
                <CardContent className="space-y-2" data-testid="local-model-benchmark-results">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant="outline" className="text-[0.68rem]">
                      {latestBenchmark.status}
                    </Badge>
                    <span className="font-mono">{latestBenchmark.job_id}</span>
                  </div>
                  {latestBenchmark.results.length > 0 ? (
                    <div className="grid gap-2">
                      {latestBenchmark.results.map(result => (
                        <div
                          key={`${latestBenchmark.job_id}-${result.role}`}
                          className="rounded-md border bg-muted/20 px-3 py-2"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="min-w-0">
                              <div className="truncate text-sm font-medium">
                                {result.label}
                              </div>
                              <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                                {result.model_runtime && (
                                  <ModelFleetBadge runtime={result.model_runtime} />
                                )}
                                <span className="truncate font-mono">
                                  {result.model_name || result.error || result.status}
                                </span>
                              </div>
                            </div>
                            <div className="shrink-0 text-right text-xs">
                              {result.status === 'completed' ? (
                                <>
                                  <div className="font-mono">
                                    {result.tokens_per_second?.toFixed(0)} tok/s
                                  </div>
                                  <div className="text-muted-foreground">
                                    {result.latency_ms} ms
                                  </div>
                                </>
                              ) : (
                                <Badge variant="outline" className="text-[0.68rem]">
                                  {result.status}
                                </Badge>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground">
                      {t('localModels.benchmarkWaiting', {
                        defaultValue: 'Benchmark queued. Results will appear here.',
                      })}
                    </div>
                  )}
                </CardContent>
              )}
            </Card>
          )}

          {/* Inventory list */}
          {data && data.available && data.models.length > 0 && (
            <div className="space-y-3" data-testid="local-models-list">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Tabs
                  value={inventoryFilter}
                  onValueChange={value => setInventoryFilter(value as InventoryFilter)}
                >
                  <TabsList aria-label="Filter local model inventory">
                    <TabsTrigger value="all" onClick={() => setInventoryFilter('all')}>
                      {t('localModels.filterAll', { defaultValue: 'All' })}
                      <Badge variant="secondary" className="ml-1 text-[0.68rem]">
                        {inventoryModels.length}
                      </Badge>
                    </TabsTrigger>
                    <TabsTrigger value="ready" onClick={() => setInventoryFilter('ready')}>
                      {t('localModels.filterReady', { defaultValue: 'Ready' })}
                      <Badge variant="secondary" className="ml-1 text-[0.68rem]">
                        {summary?.runnable ?? 0}
                      </Badge>
                    </TabsTrigger>
                    <TabsTrigger value="setup" onClick={() => setInventoryFilter('setup')}>
                      {t('localModels.filterSetup', { defaultValue: 'Setup needed' })}
                      <Badge variant="secondary" className="ml-1 text-[0.68rem]">
                        {summary?.inventoryOnly ?? 0}
                      </Badge>
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
                <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
                  <div className="relative w-full sm:w-72">
                    <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      aria-label={t('localModels.searchAria', {
                        defaultValue: 'Search local models',
                      })}
                      className="h-9 pl-8 text-sm"
                      value={inventorySearch}
                      onChange={event => setInventorySearch(event.target.value)}
                      placeholder={t('localModels.searchPlaceholder', {
                        defaultValue: 'Search name, runtime, quant…',
                      })}
                    />
                  </div>
                  <select
                    aria-label={t('localModels.sortAria', {
                      defaultValue: 'Sort local models',
                    })}
                    className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    value={inventorySort}
                    onChange={event => setInventorySort(event.target.value as InventorySort)}
                  >
                    <option value="name-asc">
                      {t('localModels.sortName', { defaultValue: 'Name A-Z' })}
                    </option>
                    <option value="runtime-asc">
                      {t('localModels.sortRuntime', { defaultValue: 'Runtime' })}
                    </option>
                    <option value="size-desc">
                      {t('localModels.sortSizeDesc', { defaultValue: 'Largest' })}
                    </option>
                    <option value="size-asc">
                      {t('localModels.sortSizeAsc', { defaultValue: 'Smallest' })}
                    </option>
                    <option value="context-desc">
                      {t('localModels.sortContextDesc', { defaultValue: 'Context' })}
                    </option>
                    <option value="params-desc">
                      {t('localModels.sortParamsDesc', { defaultValue: 'Parameters' })}
                    </option>
                  </select>
                  <div className="shrink-0 text-xs text-muted-foreground">
                    {t('localModels.filterShowing', {
                      defaultValue: 'Showing {{shown}} of {{total}}',
                      shown: filteredInventoryModels.length,
                      total: inventoryModels.length,
                    })}
                  </div>
                </div>
              </div>
              {filteredInventoryModels.length === 0 && (
                <div className="rounded-md border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">
                  <div>
                    {t('localModels.noSearchMatches', {
                      defaultValue: 'No models match the current filters.',
                    })}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-3 h-8 text-xs"
                    onClick={clearInventoryFilters}
                  >
                    {t('localModels.clearFilters', {
                      defaultValue: 'Clear filters',
                    })}
                  </Button>
                </div>
              )}
              {filteredInventoryModels.map(m => (
                <Card key={m.path} data-testid={`local-model-${m.name}`}>
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="space-y-1">
                        <CardTitle className="text-base font-medium break-all">
                          {m.name}
                        </CardTitle>
                        <CardDescription className="flex items-center gap-2 text-xs">
                          <span className="break-all">{m.path}</span>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-6 shrink-0 px-2 text-xs"
                            aria-label={t('localModels.copyPathAria', {
                              defaultValue: 'Copy model path for {{name}}',
                              name: m.name,
                            })}
                            onClick={() => copyModelPath(m)}
                          >
                            <Copy className="h-3 w-3" />
                          </Button>
                        </CardDescription>
                        {m.launcher_model_ref && m.launcher_model_ref !== m.path && (
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span className="shrink-0 font-medium">
                              {t('localModels.launcherRefLabel', {
                                defaultValue: 'Launcher ref',
                              })}
                            </span>
                            <code className="min-w-0 break-all rounded bg-muted px-1.5 py-0.5">
                              {m.launcher_model_ref}
                            </code>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="h-6 shrink-0 px-2 text-xs"
                              aria-label={t('localModels.copyLauncherRefAria', {
                                defaultValue: 'Copy launcher reference for {{name}}',
                                name: m.name,
                              })}
                              onClick={() => copyLauncherModelRef(m)}
                            >
                              <Copy className="h-3 w-3" />
                            </Button>
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <ModelFleetBadge runtime={m.runtime} />
                        {m.quant && (
                          <Badge variant="secondary" className="text-xs">
                            <Hash className="h-3 w-3 mr-1" />
                            {m.quant}
                          </Badge>
                        )}
                        {m.architecture && (
                          <Badge variant="outline" className="text-xs">
                            {m.architecture}
                          </Badge>
                        )}
                        {m.is_live_active && (
                          <Badge variant="default" className="text-xs">
                            {t('localModels.activeNowBadge', {
                              defaultValue: 'Active now',
                            })}
                          </Badge>
                        )}
                        {m.is_launch_default && (
                          <Badge variant="secondary" className="text-xs">
                            {t('localModels.launchDefaultBadge', {
                              defaultValue: 'Launch default',
                            })}
                          </Badge>
                        )}
                        {m.activation_mode === 'restart_required' && (
                          <Badge variant="outline" className="text-xs">
                            {t('localModels.restartNeededBadge', {
                              defaultValue: 'Restart needed',
                            })}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="pt-0 space-y-3">
                    <dl className="grid grid-cols-3 gap-3 text-xs">
                      <div>
                        <dt className="text-muted-foreground">
                          {t('localModels.colParams', { defaultValue: 'Parameters' })}
                        </dt>
                        <dd className="font-mono">{fmtParams(m.parameter_count_b)}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">
                          {t('localModels.colContext', { defaultValue: 'Context' })}
                        </dt>
                        <dd className="font-mono">{fmtNCtx(m.context_length)}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground flex items-center gap-1">
                          <HardDrive className="h-3 w-3" />
                          {t('localModels.colSize', { defaultValue: 'Size' })}
                        </dt>
                        <dd className="font-mono">{fmtBytes(m.file_size_bytes)}</dd>
                      </div>
                    </dl>
                    {!isRunnableLocalModel(m) && (
                      <div className="rounded-md border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                        <div className="flex items-center gap-2 font-medium text-foreground">
                          <Badge variant="outline" className="text-[0.68rem]">
                            {t('localModels.inventoryOnlyBadge', {
                              defaultValue: 'Inventory only',
                            })}
                          </Badge>
                          {t('localModels.inventoryOnlyTitle', {
                            defaultValue: 'Not runnable by the desktop launcher yet',
                          })}
                        </div>
                        <div className="mt-1 leading-5">
                          {m.runtime_note || t('localModels.inventoryOnlyDesc', {
                            defaultValue:
                              'Add a runnable provider before using this asset for chat, role routing, or local benchmarks.',
                          })}
                        </div>
                        <Button asChild variant="outline" size="sm" className="mt-2 h-7 text-xs">
                          <Link href={inventorySetupHref(m)}>
                            {inventorySetupLabel(m, t)}
                          </Link>
                        </Button>
                      </div>
                    )}
                    {(supportsLaunchDefault(m) || supportsChatActivation(m)) && (
                      <div className="flex justify-end gap-2">
                        {supportsLaunchDefault(m) && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="gap-1.5 h-7 text-xs"
                            disabled={
                              setLaunchDefault.isPending
                              || launchDefaultRef === m.launcher_model_ref
                              || Boolean(m.is_launch_default)
                            }
                            onClick={() => setLaunchDefault.mutate(m)}
                            aria-label={t('localModels.setLaunchDefaultAria', {
                              defaultValue: 'Set launch default for {{name}}',
                              name: m.name,
                            })}
                          >
                            {launchDefaultRef === m.launcher_model_ref ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <Power className="h-3 w-3" />
                            )}
                            {launchDefaultButtonLabel(m, t)}
                          </Button>
                        )}
                        {supportsChatActivation(m) && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="gap-1.5 h-7 text-xs"
                            disabled={
                              setActive.isPending || activatingPath === m.path
                            }
                            onClick={() => setActive.mutate(m.path)}
                            data-testid={`set-active-${m.name}`}
                          >
                            {activatingPath === m.path ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <Power className="h-3 w-3" />
                            )}
                            {activatingPath === m.path
                              ? t('localModels.activating', {
                                  defaultValue: 'Switching…',
                                })
                              : t('localModels.setActive', {
                                  defaultValue: 'Switch live chat model',
                                })}
                          </Button>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}

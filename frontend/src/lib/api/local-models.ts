import apiClient from '@/lib/api/client'

export type LocalModel = {
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

export type InventoryResponse = {
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

export type QualityMeasurement = {
  schema_valid?: boolean | null
  citation_fidelity?: boolean | null
  instruction_following?: boolean | null
  tool_calling?: boolean | null
  context_recall?: boolean | null
  answer_correctness?: boolean | null
  refusal_when_evidence_absent?: boolean | null
}

export type BenchmarkResult = {
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
  quality?: QualityMeasurement | null
  normalized_metrics?: Record<string, number> | null
  error?: string | null
}

export type BenchmarkJob = {
  job_id: string
  roles: string[]
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  results: BenchmarkResult[]
  error?: string | null
  created_at?: number | null
  completed_at?: number | null
  controls?: { cancel?: boolean; reset?: boolean } | null
}

export type BenchmarkListResponse = { benchmarks: BenchmarkJob[] }

export type RoleRoute = {
  role: string
  label: string
  confidence: number
  reason: string
  model: LocalModel | null
}

export type RoleRoutingResponse = {
  model_dir: string
  available: boolean
  routes: RoleRoute[]
}

export type RouteReceipt = {
  selected_model_id: string
  fallback_model_id?: string | null
  role: string
  reason: string
  benchmark_age_seconds: number
  outcome: string
  created_at?: string | null
}

export type RouteReceiptResponse = { receipts: RouteReceipt[] }

export async function getLocalModelInventory(): Promise<InventoryResponse> {
  return (await apiClient.get<InventoryResponse>('/local-models/inventory')).data
}

export async function getRoleRouting(): Promise<RoleRoutingResponse> {
  return (await apiClient.get<RoleRoutingResponse>('/local-models/role-routing')).data
}

export async function getBenchmarkJobs(): Promise<BenchmarkListResponse> {
  return (await apiClient.get<BenchmarkListResponse>('/local-models/benchmarks')).data
}

export async function startBenchmark(roles?: string[]): Promise<BenchmarkJob> {
  return (await apiClient.post<BenchmarkJob>('/local-models/benchmarks', {
    ...(roles ? { roles } : {}),
  })).data
}

export async function cancelBenchmark(jobId: string): Promise<BenchmarkJob> {
  return (await apiClient.post<BenchmarkJob>(`/local-models/benchmarks/${jobId}/cancel`)).data
}

export async function resetBenchmarks(): Promise<void> {
  await apiClient.delete('/local-models/benchmarks')
}

export async function getRouteReceipts(): Promise<RouteReceiptResponse> {
  return (await apiClient.get<RouteReceiptResponse>('/local-models/route-receipts')).data
}

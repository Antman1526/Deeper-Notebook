import apiClient from '@/lib/api/client'
import { z } from 'zod'

const executionPolicySchema = z.enum(['strict_local', 'local_preferred', 'custom'])
const computeProfileSchema = z.enum(['efficient', 'balanced', 'maximum_quality'])
const readinessSchema = z.enum([
  'ready_verified', 'ready_unverified', 'requires_runtime', 'runtime_unavailable',
  'installed_unsupported', 'incomplete', 'planned', 'removed',
])
const resourceTierSchema = z.enum(['light', 'standard', 'heavyweight'])
const modelRoleSchema = z.enum([
  'research_chat', 'evidence_extraction', 'claim_verification', 'editorial_writing',
  'embedding_retrieval', 'vision_analysis', 'code_data_analysis', 'podcast_outline',
  'podcast_script', 'speech_to_text', 'text_to_speech',
])

function rejectPathFields(value: unknown): void {
  if (Array.isArray(value)) return value.forEach(rejectPathFields)
  if (!value || typeof value !== 'object') return
  for (const [key, nested] of Object.entries(value)) {
    if (key === 'path') throw new Error('Redacted local-model response unexpectedly contained a path.')
    rejectPathFields(nested)
  }
}

function parseRedacted<T>(schema: z.ZodType<T>, value: unknown): T {
  rejectPathFields(value)
  return schema.parse(value)
}

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
  readiness?: z.infer<typeof readinessSchema>
  readiness_reason?: string
  measured_tier?: z.infer<typeof resourceTierSchema> | null
  accepted_roles?: string[]
  route_eligible?: boolean
}

const localModelSchema: z.ZodType<LocalModel> = z.object({
  name: z.string(), path: z.string(), launcher_model_ref: z.string().nullable().optional(),
  runtime: z.string().nullable().optional(), runnable: z.boolean().nullable().optional(),
  activation_supported: z.boolean().nullable().optional(), is_launch_default: z.boolean().nullable().optional(),
  is_live_active: z.boolean().nullable().optional(), activation_mode: z.string().nullable().optional(),
  activation_detail: z.string().nullable().optional(), runtime_status: z.string().nullable().optional(),
  runtime_note: z.string().nullable().optional(), setup_href: z.string().nullable().optional(),
  setup_label: z.string().nullable().optional(), architecture: z.string().nullable(), context_length: z.number().nullable(),
  quant: z.string().nullable(), parameter_count_b: z.number().nullable(), file_size_bytes: z.number(),
  readiness: readinessSchema.optional(), readiness_reason: z.string().optional(), measured_tier: resourceTierSchema.nullable().optional(),
  accepted_roles: z.array(z.string()).optional(), route_eligible: z.boolean().optional(),
}).strict()

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

export const inventoryResponseSchema: z.ZodType<InventoryResponse> = z.object({
  model_dir: z.string(), available: z.boolean(), models: z.array(localModelSchema),
  launcher_config: z.object({ available: z.boolean(), path: z.string(), provider: z.string(), default_model: z.string(), model_dir: z.string(), model_dir_matches_inventory: z.boolean(), active_gguf_model: z.string().optional() }).strict().optional(),
}).strict()

export type LocalModelSettings = {
  model_dir: string
  execution_policy: z.infer<typeof executionPolicySchema>
  compute_profile: z.infer<typeof computeProfileSchema>
  local_model_memory_limit_bytes: number | null
  role_overrides: Record<string, string>
  trusted_external_model_roots: string[]
}

export const localModelSettingsSchema: z.ZodType<LocalModelSettings> = z.object({
  model_dir: z.string(), execution_policy: executionPolicySchema, compute_profile: computeProfileSchema,
  local_model_memory_limit_bytes: z.number().int().nonnegative().nullable(), role_overrides: z.record(z.string(), z.string()),
  trusted_external_model_roots: z.array(z.string()),
}).strict()

export type ReadinessModel = {
  model_id: string
  format: string
  modality: string
  readiness: z.infer<typeof readinessSchema>
  readiness_reason: string
  measured_tier: z.infer<typeof resourceTierSchema> | null
  accepted_roles: string[]
  route_eligible: boolean
}
export type ReadinessResponse = { available: boolean; models: ReadinessModel[] }
export const readinessResponseSchema: z.ZodType<ReadinessResponse> = z.object({
  available: z.boolean(), models: z.array(z.object({ model_id: z.string(), format: z.string(), modality: z.string(), readiness: readinessSchema, readiness_reason: z.string(), measured_tier: resourceTierSchema.nullable(), accepted_roles: z.array(z.string()), route_eligible: z.boolean() }).strict()),
}).strict()

export type ModelRoutePlan = {
  role: z.infer<typeof modelRoleSchema>
  outcome: 'ready' | 'blocked' | 'approval_required'
  selected_model_id: string | null
  selected_provider: string | null
  resource_tier: z.infer<typeof resourceTierSchema> | null
  selection_source: 'automatic' | 'role_override' | 'production_override' | null
  route_reason: string
  escalation_model_ids: string[]
  blocked_reason: string | null
  selected_fingerprint: string | null
  selected_measurements: Record<string, number>
}
export const modelRoutePlanSchema: z.ZodType<ModelRoutePlan> = z.object({
  role: modelRoleSchema, outcome: z.enum(['ready', 'blocked', 'approval_required']), selected_model_id: z.string().nullable(), selected_provider: z.string().nullable(),
  resource_tier: resourceTierSchema.nullable(), selection_source: z.enum(['automatic', 'role_override', 'production_override']).nullable(), route_reason: z.string(),
  escalation_model_ids: z.array(z.string()).max(2), blocked_reason: z.string().nullable(), selected_fingerprint: z.string().nullable(), selected_measurements: z.record(z.string(), z.number()),
}).strict()

export type RoutePlanRequest = {
  role: ModelRoutePlan['role']; required_context_tokens?: number; modalities?: Array<'text' | 'image' | 'audio'>; requires_structured_output?: boolean
  execution_policy: LocalModelSettings['execution_policy']; compute_profile: LocalModelSettings['compute_profile']; role_override_model_id?: string | null; production_override_model_id?: string | null; memory_reservation_bytes?: number
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
  model: Pick<LocalModel, 'name' | 'runtime'> | null
}

export type RoleRoutingResponse = {
  model_dir: string
  available: boolean
  routes: RoleRoute[]
}

const redactedRoleModelSchema = z.object({ name: z.string(), runtime: z.string().nullable().optional() }).strict()
const roleRoutingResponseSchema: z.ZodType<RoleRoutingResponse> = z.object({
  model_dir: z.string(), available: z.boolean(), routes: z.array(z.object({
    role: z.string(), label: z.string(), confidence: z.number(), reason: z.string(), model: redactedRoleModelSchema.nullable(),
  }).strict()),
}).strict()

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

const routeReceiptSchema: z.ZodType<RouteReceipt> = z.object({
  selected_model_id: z.string(), fallback_model_id: z.string().nullable().optional(), role: z.string(), reason: z.string(),
  benchmark_age_seconds: z.number(), outcome: z.string(), created_at: z.string().nullable().optional(),
}).strict()
const routeReceiptResponseSchema: z.ZodType<RouteReceiptResponse> = z.object({ receipts: z.array(routeReceiptSchema) }).strict()

export async function getLocalModelInventory(): Promise<InventoryResponse> {
  return inventoryResponseSchema.parse((await apiClient.get('/local-models/inventory')).data)
}

export async function getLocalModelSettings(): Promise<LocalModelSettings> {
  return parseRedacted(localModelSettingsSchema, (await apiClient.get('/local-models/settings')).data)
}

export async function updateLocalModelSettings(settings: LocalModelSettings): Promise<LocalModelSettings> {
  return parseRedacted(localModelSettingsSchema, (await apiClient.put('/local-models/settings', settings)).data)
}

export async function getLocalModelReadiness(): Promise<ReadinessResponse> {
  return parseRedacted(readinessResponseSchema, (await apiClient.get('/local-models/readiness')).data)
}

export async function getModelRoutePlan(request: RoutePlanRequest): Promise<ModelRoutePlan> {
  return parseRedacted(modelRoutePlanSchema, (await apiClient.post('/local-models/route-plan', request)).data)
}

export async function getRoleRouting(): Promise<RoleRoutingResponse> {
  return parseRedacted(roleRoutingResponseSchema, (await apiClient.get('/local-models/role-routing')).data)
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
  return parseRedacted(routeReceiptResponseSchema, (await apiClient.get('/local-models/route-receipts')).data)
}

import apiClient from './client'
import {
  STUDY_ASSISTANT_ROLES,
  STUDY_AUTHORITIES,
  decodeStudyAssistantResponse,
  type StudyAssistantRequest,
  type StudyAssistantResponse,
  type StudyAssistantRole,
} from '@/lib/types/study-assistants'

export { decodeStudyAssistantResponse } from '@/lib/types/study-assistants'

function invalidRequest(): never {
  throw new Error('Invalid Study Assistant request')
}

function requestRecord(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) invalidRequest()
  return value as Record<string, unknown>
}

function visibleText(value: unknown, max: number): string {
  if (typeof value !== 'string') invalidRequest()
  if (!value || value.trim() !== value || value.length > max || /[\u0000-\u001f\u007f]/.test(value)) invalidRequest()
  return value
}

function validatePlanId(value: unknown): string {
  const planId = visibleText(value, 512)
  if (!planId.startsWith('study_plan:')) invalidRequest()
  return planId
}

function validateRole(value: unknown): StudyAssistantRole {
  if (typeof value !== 'string' || !STUDY_ASSISTANT_ROLES.includes(value as StudyAssistantRole)) invalidRequest()
  return value as StudyAssistantRole
}

function validateAuthority(value: unknown): StudyAssistantRequest['authority'] {
  if (typeof value !== 'string' || !STUDY_AUTHORITIES.includes(value as StudyAssistantRequest['authority'])) invalidRequest()
  return value as StudyAssistantRequest['authority']
}

function validateSourceIds(value: unknown): string[] {
  if (!Array.isArray(value) || value.length > 100) invalidRequest()
  const ids = value.map((item) => visibleText(item, 512))
  if (new Set(ids).size !== ids.length) invalidRequest()
  return ids
}

function validateScope(value: unknown): string[] {
  if (!Array.isArray(value) || value.length > 8) invalidRequest()
  const scope = value.map((item) => visibleText(item, 512))
  if (scope.some((item) => !item.startsWith('https://')) || new Set(scope).size !== scope.length) invalidRequest()
  return scope
}

function validateInput(input: StudyAssistantRequest): StudyAssistantRequest {
  const data = requestRecord(input)
  const allowed = new Set([
    'authority',
    'prompt',
    'unit_id',
    'selected_source_ids',
    'model_route',
    'network_allowed',
    'approved_network_scope',
    'timeout_seconds',
    'request_id',
    'created_at',
  ])
  if (Object.keys(data).some((key) => !allowed.has(key))) invalidRequest()

  const authority = validateAuthority(data.authority)
  const prompt = visibleText(data.prompt, 16_384)
  const unitId = data.unit_id === undefined || data.unit_id === null
    ? data.unit_id
    : visibleText(data.unit_id, 64)
  if (typeof unitId === 'string' && !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(unitId)) invalidRequest()
  const selectedSourceIds = validateSourceIds(data.selected_source_ids)
  const modelRoute = data.model_route
  if (modelRoute !== 'local' && modelRoute !== 'cloud') invalidRequest()
  if (typeof data.network_allowed !== 'boolean') invalidRequest()
  const approvedNetworkScope = validateScope(data.approved_network_scope)
  if (data.network_allowed !== (approvedNetworkScope.length > 0)) invalidRequest()
  if (modelRoute === 'cloud' && !data.network_allowed) invalidRequest()
  if (!Number.isInteger(data.timeout_seconds) || (data.timeout_seconds as number) < 1 || (data.timeout_seconds as number) > 120) invalidRequest()
  const requestId = data.request_id === undefined ? undefined : visibleText(data.request_id, 256)
  const createdAt = data.created_at === undefined ? undefined : visibleText(data.created_at, 64)
  if (createdAt !== undefined && (Number.isNaN(Date.parse(createdAt)) || !/[zZ]|[+-]\d{2}:?\d{2}$/.test(createdAt))) invalidRequest()

  return {
    authority,
    prompt,
    ...(unitId === undefined ? {} : { unit_id: unitId }),
    selected_source_ids: selectedSourceIds,
    model_route: modelRoute,
    network_allowed: data.network_allowed,
    approved_network_scope: approvedNetworkScope,
    timeout_seconds: data.timeout_seconds as number,
    ...(requestId === undefined ? {} : { request_id: requestId }),
    ...(createdAt === undefined ? {} : { created_at: createdAt }),
  }
}

function assistantPath(planId: string, role: StudyAssistantRole): string {
  return `/study/plans/${encodeURIComponent(planId)}/assistants/${role}:invoke`
}

export const studyAssistantsApi = {
  async invoke(
    planId: string,
    role: StudyAssistantRole,
    input: StudyAssistantRequest,
    signal?: AbortSignal,
  ): Promise<StudyAssistantResponse> {
    const normalizedPlanId = validatePlanId(planId)
    const normalizedRole = validateRole(role)
    const body = validateInput(input)
    const response = await apiClient.post(assistantPath(normalizedPlanId, normalizedRole), body, {
      signal,
      headers: { 'x-skip-error-toast': '1' },
    })
    return decodeStudyAssistantResponse(response.data)
  },
}

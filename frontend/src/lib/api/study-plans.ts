import apiClient from './client'
import {
  AddStudyPlanSourceInput,
  ApproveStudySyllabusInput,
  CreateStudyPlanInput,
  decodeStudyPlan,
  decodeStudyPlanList,
  decodeStudyPlanSourceLink,
  decodeStudySourceReadiness,
  decodeStudySyllabus,
  ProposeStudySyllabusInput,
  RemoveStudyPlanSourceInput,
  SaveStudySyllabusInput,
  StudyPlan,
  StudyPlanSourceLink,
  studyPlanPreferencesSchema,
  studySyllabusUnitSchema,
  StudySourceReadiness,
  StudySyllabus,
  UpdateStudyPlanInput,
} from '@/lib/types/study-plans'
import {
  decodeStudyMasteryProjection,
  StudyProgressDecisionInput,
  StudyProgressDecisionResponse,
} from '@/lib/types/study-progress'

function planPath(planId: string): string {
  return `/study/plans/${encodeURIComponent(planId)}`
}

function sourcePath(planId: string, sourceId: string): string {
  return `${planPath(planId)}/sources/${encodeURIComponent(sourceId)}`
}

function invalidRequest(): never {
  throw new Error('Invalid Study Plan request')
}

function requestRecord(value: unknown, allowedKeys: readonly string[]): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) invalidRequest()
  const record = value as Record<string, unknown>
  const allowed = new Set(allowedKeys)
  if (Object.keys(record).some((key) => !allowed.has(key))) invalidRequest()
  return record
}

function hasOwn(record: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key)
}

function validateText(value: unknown, max: number): string {
  if (typeof value !== 'string') invalidRequest()
  const normalized = value.trim()
  if (!normalized || normalized.length > max || /[\u0000-\u001f\u007f]/.test(normalized)) {
    invalidRequest()
  }
  return normalized
}

function validatePlanId(value: unknown): string {
  return validateText(value, 512)
}

function validateCalendarDate(value: unknown): string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) invalidRequest()
  const parsed = new Date(`${value}T00:00:00.000Z`)
  if (Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value) {
    invalidRequest()
  }
  return value
}

function validatePreferences(value: unknown): CreateStudyPlanInput['preferences'] {
  if (value === null) return null
  if (value === undefined) invalidRequest()
  const parsed = studyPlanPreferencesSchema.safeParse(value)
  if (!parsed.success) invalidRequest()
  return parsed.data
}

function validateCreateInput(input: CreateStudyPlanInput): CreateStudyPlanInput {
  const data = requestRecord(input, ['goal', 'starting_level', 'target_date', 'preferences'])
  return {
    goal: validateText(data.goal, 2_000),
    starting_level: validateText(data.starting_level, 200),
    ...(hasOwn(data, 'target_date')
      ? { target_date: data.target_date === null ? null : validateCalendarDate(data.target_date) }
      : {}),
    ...(hasOwn(data, 'preferences') ? { preferences: validatePreferences(data.preferences) } : {}),
  }
}

function validateRevision(value: unknown): number {
  if (!Number.isInteger(value) || (value as number) < 1) invalidRequest()
  return value as number
}

function validateRequestId(value: unknown): string {
  return validateText(value, 256)
}

function validateProgressDecision(input: StudyProgressDecisionInput): StudyProgressDecisionInput {
  try {
    const data = requestRecord(input, ['proposal_id', 'decision', 'request_id', 'expected_revision'])
    const decision = data.decision
    if (decision !== 'accepted' && decision !== 'dismissed') invalidRequest()
    const result: StudyProgressDecisionInput = {
      proposal_id: validateText(data.proposal_id, 512),
      decision,
      request_id: validateRequestId(data.request_id),
    }
    if (decision === 'accepted') {
      result.expected_revision = validateRevision(data.expected_revision)
    } else if (Object.prototype.hasOwnProperty.call(data, 'expected_revision') && data.expected_revision !== undefined) {
      invalidRequest()
    }
    return result
  } catch (error) {
    if (error instanceof Error && error.message === 'Invalid Study Plan request') {
      throw new Error('Invalid Study progress request')
    }
    throw error
  }
}

function decodeProgressDecision(value: unknown): StudyProgressDecisionResponse {
  const record = requestRecord(value, ['proposal_id', 'decision', 'projection'])
  const decision = record.decision
  if (decision !== 'accepted' && decision !== 'dismissed') invalidRequest()
  return {
    proposal_id: validateText(record.proposal_id, 512),
    decision,
    projection: decodeStudyMasteryProjection(record.projection),
  }
}

export const studyPlansApi = {
  async list(): Promise<StudyPlan[]> {
    const response = await apiClient.get('/study/plans')
    return decodeStudyPlanList(response.data)
  },

  async get(planId: string): Promise<StudyPlan> {
    const response = await apiClient.get(planPath(validatePlanId(planId)))
    return decodeStudyPlan(response.data)
  },

  async create(input: CreateStudyPlanInput): Promise<StudyPlan> {
    const response = await apiClient.post('/study/plans', validateCreateInput(input))
    return decodeStudyPlan(response.data)
  },

  async update(planId: string, input: UpdateStudyPlanInput): Promise<StudyPlan> {
    const normalizedPlanId = validatePlanId(planId)
    const data = requestRecord(input, ['expected_revision', 'goal', 'starting_level', 'target_date', 'preferences'])
    const body: UpdateStudyPlanInput = {
      expected_revision: validateRevision(data.expected_revision),
      ...(hasOwn(data, 'goal') ? { goal: validateText(data.goal, 2_000) } : {}),
      ...(hasOwn(data, 'starting_level') ? { starting_level: validateText(data.starting_level, 200) } : {}),
      ...(hasOwn(data, 'target_date')
        ? { target_date: data.target_date === null ? null : validateCalendarDate(data.target_date) }
        : {}),
      ...(hasOwn(data, 'preferences') ? { preferences: validatePreferences(data.preferences) } : {}),
    }
    if (Object.keys(body).length === 1) throw new Error('Invalid Study Plan request')
    const response = await apiClient.patch(planPath(normalizedPlanId), body)
    return decodeStudyPlan(response.data)
  },

  async addSource(planId: string, input: AddStudyPlanSourceInput): Promise<StudyPlanSourceLink> {
    const data = requestRecord(input, ['source_id', 'expected_revision'])
    const response = await apiClient.post(`${planPath(validatePlanId(planId))}/sources`, {
      source_id: validatePlanId(data.source_id),
      expected_revision: validateRevision(data.expected_revision),
    })
    return decodeStudyPlanSourceLink(response.data)
  },

  async removeSource(planId: string, input: RemoveStudyPlanSourceInput): Promise<{ removed: boolean }> {
    const data = requestRecord(input, ['source_id', 'expected_revision'])
    const response = await apiClient.delete(sourcePath(validatePlanId(planId), validatePlanId(data.source_id)), {
      data: { expected_revision: validateRevision(data.expected_revision) },
    })
    const removed = response.data
    if (!removed || typeof removed !== 'object' || typeof removed.removed !== 'boolean' || Object.keys(removed).length !== 1) {
      throw new Error('Invalid Study Plan response')
    }
    return removed as { removed: boolean }
  },

  async readiness(planId: string): Promise<StudySourceReadiness> {
    const response = await apiClient.get(`${planPath(validatePlanId(planId))}/sources/readiness`)
    return decodeStudySourceReadiness(response.data)
  },

  async syllabus(planId: string, version?: number): Promise<StudySyllabus | null> {
    const response = await apiClient.get(`${planPath(validatePlanId(planId))}/syllabus`, {
      params: version === undefined ? undefined : { version: validateRevision(version) },
    })
    if (response.status === 204) return null
    return decodeStudySyllabus(response.data)
  },

  async proposeSyllabus(planId: string, input: ProposeStudySyllabusInput): Promise<StudySyllabus> {
    const data = requestRecord(input, ['expected_revision'])
    const response = await apiClient.post(`${planPath(validatePlanId(planId))}/syllabus:propose`, {
      expected_revision: validateRevision(data.expected_revision),
    })
    return decodeStudySyllabus(response.data)
  },

  async saveSyllabus(planId: string, input: SaveStudySyllabusInput): Promise<StudySyllabus> {
    const data = requestRecord(input, ['expected_revision', 'version', 'source_manifest_sha256', 'units'])
    if (typeof data.source_manifest_sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(data.source_manifest_sha256)) invalidRequest()
    const units = studySyllabusUnitSchema.array().min(1).max(64).safeParse(data.units)
    if (!units.success) invalidRequest()
    const response = await apiClient.put(`${planPath(validatePlanId(planId))}/syllabus`, {
      expected_revision: validateRevision(data.expected_revision),
      version: validateRevision(data.version),
      source_manifest_sha256: data.source_manifest_sha256,
      units: units.data,
    })
    return decodeStudySyllabus(response.data)
  },

  async approveSyllabus(planId: string, input: ApproveStudySyllabusInput): Promise<StudyPlan> {
    const data = requestRecord(input, ['syllabus_version', 'expected_revision'])
    const response = await apiClient.post(`${planPath(validatePlanId(planId))}/syllabus:approve`, {
      syllabus_version: validateRevision(data.syllabus_version),
      expected_revision: validateRevision(data.expected_revision),
    })
    return decodeStudyPlan(response.data)
  },

  async progress(planId: string) {
    const response = await apiClient.get(`${planPath(validatePlanId(planId))}/progress`)
    return decodeStudyMasteryProjection(response.data)
  },

  async decideProgress(planId: string, input: StudyProgressDecisionInput): Promise<StudyProgressDecisionResponse> {
    const response = await apiClient.post(`${planPath(validatePlanId(planId))}/progress:decision`, validateProgressDecision(input))
    return decodeProgressDecision(response.data)
  },
}

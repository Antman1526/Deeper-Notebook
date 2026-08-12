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

function planPath(planId: string): string {
  return `/study/plans/${encodeURIComponent(planId)}`
}

function sourcePath(planId: string, sourceId: string): string {
  return `${planPath(planId)}/sources/${encodeURIComponent(sourceId)}`
}

function validateText(value: string, max: number): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > max || /[\u0000-\u001f\u007f]/.test(normalized)) {
    throw new Error('Invalid Study Plan request')
  }
  return normalized
}

function validatePlanId(value: string): string {
  return validateText(value, 512)
}

function validateCalendarDate(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Invalid Study Plan request')
  const parsed = new Date(`${value}T00:00:00.000Z`)
  if (Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value) {
    throw new Error('Invalid Study Plan request')
  }
  return value
}

function validatePreferences(value: unknown): CreateStudyPlanInput['preferences'] {
  if (value === null || value === undefined) return value
  const parsed = studyPlanPreferencesSchema.safeParse(value)
  if (!parsed.success) throw new Error('Invalid Study Plan request')
  return parsed.data
}

function validateCreateInput(input: CreateStudyPlanInput): CreateStudyPlanInput {
  if (!input || typeof input !== 'object') throw new Error('Invalid Study Plan request')
  const data = input as unknown as Record<string, unknown>
  const allowed = new Set(['goal', 'starting_level', 'target_date', 'preferences'])
  if (Object.keys(data).some((key) => !allowed.has(key))) throw new Error('Invalid Study Plan request')
  return {
    goal: validateText(input.goal, 2_000),
    starting_level: validateText(input.starting_level, 200),
    ...(input.target_date ? { target_date: validateCalendarDate(input.target_date) } : {}),
    ...(input.preferences === undefined ? {} : { preferences: validatePreferences(input.preferences) }),
  }
}

function validateRevision(value: number): number {
  if (!Number.isInteger(value) || value < 1) throw new Error('Invalid Study Plan request')
  return value
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
    if (!input || typeof input !== 'object') throw new Error('Invalid Study Plan request')
    const data = input as unknown as Record<string, unknown>
    const allowed = new Set(['expected_revision', 'goal', 'starting_level', 'target_date', 'preferences'])
    if (Object.keys(data).some((key) => !allowed.has(key))) throw new Error('Invalid Study Plan request')
    const body: UpdateStudyPlanInput = {
      expected_revision: validateRevision(input.expected_revision),
      ...(input.goal === undefined ? {} : { goal: validateText(input.goal, 2_000) }),
      ...(input.starting_level === undefined ? {} : { starting_level: validateText(input.starting_level, 200) }),
      ...(input.target_date === undefined
        ? {}
        : { target_date: input.target_date === null ? null : validateCalendarDate(input.target_date) }),
      ...(input.preferences === undefined ? {} : { preferences: validatePreferences(input.preferences) }),
    }
    if (Object.keys(body).length === 1) throw new Error('Invalid Study Plan request')
    const response = await apiClient.patch(planPath(normalizedPlanId), body)
    return decodeStudyPlan(response.data)
  },

  async addSource(planId: string, input: AddStudyPlanSourceInput): Promise<StudyPlanSourceLink> {
    if (!input || typeof input !== 'object') throw new Error('Invalid Study Plan request')
    const response = await apiClient.post(`${planPath(validatePlanId(planId))}/sources`, {
      source_id: validatePlanId(input.source_id),
      expected_revision: validateRevision(input.expected_revision),
    })
    return decodeStudyPlanSourceLink(response.data)
  },

  async removeSource(planId: string, input: RemoveStudyPlanSourceInput): Promise<{ removed: boolean }> {
    if (!input || typeof input !== 'object') throw new Error('Invalid Study Plan request')
    const response = await apiClient.delete(sourcePath(validatePlanId(planId), validatePlanId(input.source_id)), {
      data: { expected_revision: validateRevision(input.expected_revision) },
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

  async syllabus(planId: string, version?: number): Promise<StudySyllabus> {
    const response = await apiClient.get(`${planPath(validatePlanId(planId))}/syllabus`, {
      params: version === undefined ? undefined : { version: validateRevision(version) },
    })
    return decodeStudySyllabus(response.data)
  },

  async proposeSyllabus(planId: string, input: ProposeStudySyllabusInput): Promise<StudySyllabus> {
    if (!input || typeof input !== 'object') throw new Error('Invalid Study Plan request')
    const response = await apiClient.post(`${planPath(validatePlanId(planId))}/syllabus:propose`, {
      expected_revision: validateRevision(input.expected_revision),
    })
    return decodeStudySyllabus(response.data)
  },

  async saveSyllabus(planId: string, input: SaveStudySyllabusInput): Promise<StudySyllabus> {
    if (!input || typeof input !== 'object' || !/^[0-9a-f]{64}$/.test(input.source_manifest_sha256)) {
      throw new Error('Invalid Study Plan request')
    }
    const units = studySyllabusUnitSchema.array().min(1).max(64).safeParse(input.units)
    if (!units.success) throw new Error('Invalid Study Plan request')
    const response = await apiClient.put(`${planPath(validatePlanId(planId))}/syllabus`, {
      expected_revision: validateRevision(input.expected_revision),
      version: validateRevision(input.version),
      source_manifest_sha256: input.source_manifest_sha256,
      units: units.data,
    })
    return decodeStudySyllabus(response.data)
  },

  async approveSyllabus(planId: string, input: ApproveStudySyllabusInput): Promise<StudyPlan> {
    if (!input || typeof input !== 'object') throw new Error('Invalid Study Plan request')
    const response = await apiClient.post(`${planPath(validatePlanId(planId))}/syllabus:approve`, {
      syllabus_version: validateRevision(input.syllabus_version),
      expected_revision: validateRevision(input.expected_revision),
    })
    return decodeStudyPlan(response.data)
  },
}

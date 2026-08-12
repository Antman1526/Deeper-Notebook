import { z } from 'zod'

/**
 * Study-plan responses are a public projection.  Keep this schema exact: the
 * server must never be able to smuggle source bodies, paths, or persistence
 * metadata into a browser plan object.
 */
const boundedId = z.string().min(1).max(512).refine(
  (value) => value.trim() === value && !/[\u0000-\u001f\u007f]/.test(value),
  'identifier must be visible text',
)
const visibleText = (max: number) => z.string().min(1).max(max).refine(
  (value) => value.trim().length > 0 && !/[\u0000-\u001f\u007f]/.test(value),
  'text must be visible',
)
const boundedUnitId = visibleText(64).refine(
  (value) => /^[a-z0-9][a-z0-9_-]{0,63}$/.test(value),
  'invalid unit id',
)
const calendarDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine((value) => {
  const parsed = new Date(`${value}T00:00:00.000Z`)
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
}, 'date must be a valid calendar date')
const timestamp = z.string().datetime({ offset: true })

export const studyPlanStateSchema = z.enum([
  'draft',
  'analyzing_sources',
  'syllabus_proposed',
  'editing',
  'approved',
  'generating',
  'active',
  'completed',
  'archived',
])

export const studyPlanPreferencesSchema = z.object({
  weekly_minutes: z.number().int().min(5).max(10_080),
  session_minutes: z.number().int().min(5).max(480),
  // Task 11 supplies defaults for these fields when callers use the older
  // two-field preference shape. Responses still project the persisted values.
  model_route: z.enum(['local', 'cloud']).default('local'),
  network_allowed: z.boolean().default(false),
  approved_network_scope: z.array(
    visibleText(512).refine((value) => value.startsWith('https://'), 'scope must use HTTPS'),
  ).max(8).default([]),
}).strict().superRefine((preferences, context) => {
  if (preferences.network_allowed !== (preferences.approved_network_scope.length > 0)) {
    context.addIssue({ code: 'custom', path: ['approved_network_scope'], message: 'network authority and scope must be supplied together' })
  }
  if (preferences.model_route === 'cloud' && !preferences.network_allowed) {
    context.addIssue({ code: 'custom', path: ['model_route'], message: 'cloud route requires network authority' })
  }
  if (new Set(preferences.approved_network_scope).size !== preferences.approved_network_scope.length) {
    context.addIssue({ code: 'custom', path: ['approved_network_scope'], message: 'approved network scope entries must be unique' })
  }
})

export const studyPlanSourceLinkSchema = z.object({
  source_id: boundedId,
}).strict()

const studyActivitySchema = z.object({
  activity_id: boundedUnitId,
  kind: z.enum(['reading', 'lesson', 'tutor_session', 'quiz', 'recall', 'exam', 'project', 'review', 'custom']),
  title: visibleText(200),
  estimated_minutes: z.number().int().min(5).max(10_080),
  source_ids: z.array(boundedId).max(100),
}).strict()

export const studySyllabusUnitSchema = z.object({
  unit_id: boundedUnitId,
  title: visibleText(200),
  objectives: z.array(visibleText(2_000)).min(1).max(20),
  prerequisite_unit_ids: z.array(boundedUnitId).max(20),
  estimated_minutes: z.number().int().min(5).max(10_080),
  source_ids: z.array(boundedId).max(100),
  activities: z.array(studyActivitySchema).max(50),
}).strict().superRefine((unit, context) => {
  if (new Set(unit.objectives).size !== unit.objectives.length) {
    context.addIssue({ code: 'custom', message: 'unit objectives must be unique' })
  }
  if (new Set(unit.prerequisite_unit_ids).size !== unit.prerequisite_unit_ids.length) {
    context.addIssue({ code: 'custom', message: 'unit prerequisites must be unique' })
  }
  if (new Set(unit.source_ids).size !== unit.source_ids.length) {
    context.addIssue({ code: 'custom', message: 'unit sources must be unique' })
  }
  if (new Set(unit.activities.map((activity) => activity.activity_id)).size !== unit.activities.length) {
    context.addIssue({ code: 'custom', message: 'unit activities must be unique' })
  }
})

export const studyPlanSchema = z.object({
  plan_id: boundedId,
  goal: visibleText(2_000),
  starting_level: visibleText(200),
  target_date: calendarDate.nullable(),
  preferences: studyPlanPreferencesSchema.nullable(),
  source_links: z.array(studyPlanSourceLinkSchema).max(100),
  approved_syllabus_version: z.number().int().min(1).nullable(),
  state: studyPlanStateSchema,
  version: z.number().int().min(1),
  created_at: timestamp,
  updated_at: timestamp,
}).strict().superRefine((plan, context) => {
  if (new Set(plan.source_links.map((link) => link.source_id)).size !== plan.source_links.length) {
    context.addIssue({ code: 'custom', message: 'plan sources must be unique' })
  }
})

export const studySyllabusSchema = z.object({
  plan_id: boundedId,
  version: z.number().int().min(1),
  source_manifest_sha256: z.string().regex(/^[0-9a-f]{64}$/),
  units: z.array(studySyllabusUnitSchema).min(1).max(64),
  approved_at: timestamp.nullable(),
}).strict().superRefine((syllabus, context) => {
  if (new Set(syllabus.units.map((unit) => unit.unit_id)).size !== syllabus.units.length) {
    context.addIssue({ code: 'custom', message: 'syllabus units must be unique' })
  }
})

export const studySourceReadinessItemSchema = z.object({
  source_id: boundedId,
  title: visibleText(200),
  kind: z.enum(['link', 'upload', 'text', 'web_import', 'deep_research_report']),
  ready: z.boolean(),
  command_id: boundedId.nullable(),
  fingerprint_status: z.enum(['available', 'unknown']),
  reason: z.enum(['ready', 'processing', 'processing_failed', 'missing', 'unavailable']),
}).strict()

export const studySourceReadinessSchema = z.object({
  ready: z.boolean(),
  items: z.array(studySourceReadinessItemSchema).max(100),
}).strict()

export type StudyPlanState = z.infer<typeof studyPlanStateSchema>
export type StudyPlanPreferences = z.infer<typeof studyPlanPreferencesSchema>
export type StudyPlanSourceLink = z.infer<typeof studyPlanSourceLinkSchema>
export type StudyPlan = z.infer<typeof studyPlanSchema>
export type StudySyllabusUnit = z.infer<typeof studySyllabusUnitSchema>
export type StudySyllabus = z.infer<typeof studySyllabusSchema>
export type StudySourceReadiness = z.infer<typeof studySourceReadinessSchema>

export interface CreateStudyPlanInput {
  goal: string
  starting_level: string
  target_date?: string | null
  preferences?: StudyPlanPreferences | null
}

export interface UpdateStudyPlanInput {
  expected_revision: number
  goal?: string
  starting_level?: string
  target_date?: string | null
  preferences?: StudyPlanPreferences | null
}

export interface AddStudyPlanSourceInput {
  source_id: string
  expected_revision: number
}

export interface RemoveStudyPlanSourceInput {
  source_id: string
  expected_revision: number
}

export interface SaveStudySyllabusInput {
  expected_revision: number
  version: number
  source_manifest_sha256: string
  units: StudySyllabusUnit[]
}

export interface ProposeStudySyllabusInput {
  expected_revision: number
}

export interface ApproveStudySyllabusInput {
  syllabus_version: number
  expected_revision: number
}

export type StudyPlanList = StudyPlan[]

function invalidResponse(): Error {
  return new Error('Invalid Study Plan response')
}

function decode<T>(schema: z.ZodType<T>, value: unknown): T {
  const parsed = schema.safeParse(value)
  if (!parsed.success) throw invalidResponse()
  return parsed.data
}

export function decodeStudyPlan(value: unknown): StudyPlan {
  return decode(studyPlanSchema, value)
}

export function decodeStudyPlanList(value: unknown): StudyPlanList {
  return decode(z.array(studyPlanSchema).max(500), value)
}

export function decodeStudySyllabus(value: unknown): StudySyllabus {
  return decode(studySyllabusSchema, value)
}

export function decodeStudySourceReadiness(value: unknown): StudySourceReadiness {
  return decode(studySourceReadinessSchema, value)
}

export function decodeStudyPlanSourceLink(value: unknown): StudyPlanSourceLink {
  return decode(studyPlanSourceLinkSchema, value)
}

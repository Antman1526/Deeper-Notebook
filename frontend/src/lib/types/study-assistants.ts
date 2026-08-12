import { z } from 'zod'

export const STUDY_ASSISTANT_ROLES = [
  'study_director',
  'curriculum_architect',
  'socratic_tutor',
  'concept_explainer',
  'source_guide',
  'practice_coach',
  'exam_coach',
  'memory_coach',
  'research_scout',
  'project_mentor',
  'writing_coach',
  'progress_coach',
] as const

export type StudyAssistantRole = typeof STUDY_ASSISTANT_ROLES[number]

export const STUDY_AUTHORITIES = ['ask', 'coach', 'plan', 'create'] as const
export type StudyAuthority = typeof STUDY_AUTHORITIES[number]

export const TUTOR_MODES = [
  'teach_me',
  'ask_question',
  'quiz_me',
  'socratic',
  'solve_with_me',
  'hint',
  'explain_mistake',
  'oral_exam',
  'practice_test',
  'plan_today',
  'review_writing',
  'flashcards',
  'create_project',
  'research_gap',
] as const

export type TutorMode = typeof TUTOR_MODES[number]

export interface TutorModeConfig {
  label: string
  role: StudyAssistantRole
  authority: StudyAuthority
  model_route: 'local' | 'cloud'
  source_only: boolean
  requires_web_permission: boolean
}

/**
 * The UI mode is only a presentation choice.  These are the complete,
 * explicit Task 11 request authorities; no mode is sent to the API.
 */
export const TUTOR_MODE_CONFIG: Record<TutorMode, TutorModeConfig> = {
  teach_me: { label: 'Teach me', role: 'concept_explainer', authority: 'coach', model_route: 'local', source_only: false, requires_web_permission: false },
  ask_question: { label: 'Ask a question', role: 'source_guide', authority: 'ask', model_route: 'local', source_only: true, requires_web_permission: false },
  quiz_me: { label: 'Quiz me', role: 'practice_coach', authority: 'coach', model_route: 'local', source_only: false, requires_web_permission: false },
  socratic: { label: 'Socratic mode', role: 'socratic_tutor', authority: 'coach', model_route: 'local', source_only: false, requires_web_permission: false },
  solve_with_me: { label: 'Solve it with me', role: 'concept_explainer', authority: 'coach', model_route: 'local', source_only: false, requires_web_permission: false },
  hint: { label: 'Give me a hint', role: 'practice_coach', authority: 'coach', model_route: 'local', source_only: false, requires_web_permission: false },
  explain_mistake: { label: 'Explain my mistake', role: 'practice_coach', authority: 'coach', model_route: 'local', source_only: false, requires_web_permission: false },
  oral_exam: { label: 'Oral exam', role: 'exam_coach', authority: 'coach', model_route: 'local', source_only: false, requires_web_permission: false },
  practice_test: { label: 'Build a practice test', role: 'exam_coach', authority: 'create', model_route: 'local', source_only: false, requires_web_permission: false },
  plan_today: { label: "Plan today's session", role: 'study_director', authority: 'plan', model_route: 'local', source_only: false, requires_web_permission: false },
  review_writing: { label: 'Review this writing', role: 'writing_coach', authority: 'coach', model_route: 'local', source_only: false, requires_web_permission: false },
  flashcards: { label: 'Turn this into flashcards', role: 'memory_coach', authority: 'create', model_route: 'local', source_only: false, requires_web_permission: false },
  create_project: { label: 'Create a project', role: 'project_mentor', authority: 'create', model_route: 'local', source_only: false, requires_web_permission: false },
  research_gap: { label: 'Research this gap', role: 'research_scout', authority: 'ask', model_route: 'cloud', source_only: false, requires_web_permission: true },
}

/**
 * Role selection is an atomic policy choice. A role that is not the mode's
 * built-in specialist uses this explicit compatible mode rather than creating
 * an impossible role/authority/model/network combination.
 */
export const ROLE_DEFAULT_MODES: Record<StudyAssistantRole, TutorMode> = {
  study_director: 'plan_today',
  curriculum_architect: 'plan_today',
  socratic_tutor: 'socratic',
  concept_explainer: 'teach_me',
  source_guide: 'ask_question',
  practice_coach: 'quiz_me',
  exam_coach: 'oral_exam',
  memory_coach: 'flashcards',
  research_scout: 'research_gap',
  project_mentor: 'create_project',
  writing_coach: 'review_writing',
  progress_coach: 'plan_today',
}

export interface StudyAssistantCitation {
  source_id: string
  locator: string | null
  quote: string | null
  title: string | null
}

export interface StudyProposedAction {
  action: string
  label: string
  unit_id: string | null
  expected_revision: number | null
}

export interface StudyRetrievalReceipt {
  source_ids: string[]
  citation_count: number
}

export interface StudyAssistantResponse {
  schema_version: 1
  response_id: string | null
  session_id: string | null
  plan_id: string
  role: StudyAssistantRole
  authority: StudyAuthority
  status: 'completed' | 'failed' | 'cancelled'
  answer: string
  citations: StudyAssistantCitation[]
  proposed_actions: StudyProposedAction[]
  retrieval_receipt: StudyRetrievalReceipt
  error_code: string | null
  created_at: string
  completed_at: string | null
}

export interface StudyAssistantRequest {
  authority: StudyAuthority
  prompt: string
  unit_id?: string | null
  selected_source_ids: string[]
  model_route: 'local' | 'cloud'
  network_allowed: boolean
  approved_network_scope: string[]
  timeout_seconds: number
  request_id?: string
  created_at?: string
}

const boundedText = (max: number) => z.string().min(1).max(max).refine(
  (value) => value.trim().length > 0,
  'text must not be blank',
)
const boundedIdentifier = (max: number) => z.string().min(1).max(max).refine(
  (value) => value.trim() === value && !/[\u0000-\u001f\u007f]/.test(value),
  'identifier must be visible and trimmed',
)
const boundedId = boundedIdentifier(512)
const unitId = boundedText(64).refine((value) => /^[a-z0-9][a-z0-9_-]{0,63}$/.test(value), 'invalid unit id')

export const studyAssistantCitationSchema = z.object({
  source_id: boundedId,
  locator: boundedText(256).nullable(),
  quote: boundedText(2_000).nullable(),
  title: boundedText(200).nullable(),
}).strict()

export const studyProposedActionSchema = z.object({
  action: boundedText(96).refine((value) => /^[a-z][a-z0-9_.-]{0,95}$/.test(value), 'invalid action'),
  label: boundedText(200),
  unit_id: unitId.nullable(),
  expected_revision: z.number().int().min(1).nullable(),
}).strict()

export const studyRetrievalReceiptSchema = z.object({
  source_ids: z.array(boundedId).max(100),
  citation_count: z.number().int().min(0).max(32),
}).strict()

export const studyAssistantResponseSchema = z.object({
  schema_version: z.literal(1),
  response_id: boundedId.nullable(),
  session_id: boundedId.nullable(),
  plan_id: boundedId.refine((value) => value.startsWith('study_plan:'), 'invalid plan id'),
  role: z.enum(STUDY_ASSISTANT_ROLES),
  authority: z.enum(STUDY_AUTHORITIES),
  status: z.enum(['completed', 'failed', 'cancelled']),
  answer: boundedText(64_000),
  citations: z.array(studyAssistantCitationSchema).max(32),
  proposed_actions: z.array(studyProposedActionSchema).max(20),
  retrieval_receipt: studyRetrievalReceiptSchema,
  error_code: boundedText(96).nullable(),
  created_at: z.string().datetime({ offset: true }),
  completed_at: z.string().datetime({ offset: true }).nullable(),
}).strict()

export function decodeStudyAssistantResponse(value: unknown): StudyAssistantResponse {
  const parsed = studyAssistantResponseSchema.safeParse(value)
  if (!parsed.success) throw new Error('Invalid Study Assistant response')
  return parsed.data
}

export function modeConfig(mode: TutorMode): TutorModeConfig {
  return TUTOR_MODE_CONFIG[mode]
}

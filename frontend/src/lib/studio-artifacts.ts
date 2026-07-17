import type { StudioArtifactType } from './api/studio'

export interface StructuredArtifactValidation {
  status: 'valid' | 'invalid'
  errors: Array<Record<string, unknown>>
  strategy?: 'native' | 'json' | 'json_repair'
  attempts?: number
}

export interface StructuredArtifactEnvelope {
  schema_version: 1
  document: Record<string, unknown> & {
    schema_version: 1
    artifact_type: StudioArtifactType
    title: string
  }
  markdown: string
  content: string
  validation: StructuredArtifactValidation
}

const ARTIFACT_TYPES = new Set<StudioArtifactType>([
  'report',
  'study_guide',
  'course_pack',
  'training_guide',
  'briefing',
  'faq',
  'flashcards',
  'quiz',
  'data_table',
  'mind_map',
  'timeline',
  'infographic',
  'slide_deck',
  'podcast_outline',
  'podcast_audio',
  'research_run',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isValidation(value: unknown): value is StructuredArtifactValidation {
  if (!isRecord(value)) return false
  return (
    (value.status === 'valid' || value.status === 'invalid')
    && Array.isArray(value.errors)
    && value.errors.every(isRecord)
  )
}

export function structuredArtifactMeta(
  payload?: Record<string, unknown>,
): StructuredArtifactEnvelope | null {
  if (!payload || payload.schema_version !== 1) return null
  const document = payload.document
  if (!isRecord(document)) return null
  if (document.schema_version !== 1) return null
  if (typeof document.artifact_type !== 'string') return null
  if (!ARTIFACT_TYPES.has(document.artifact_type as StudioArtifactType)) return null
  if (typeof document.title !== 'string' || !document.title.trim()) return null
  if (typeof payload.markdown !== 'string') return null
  if (typeof payload.content !== 'string') return null
  if (!isValidation(payload.validation)) return null
  return payload as unknown as StructuredArtifactEnvelope
}

export function artifactMarkdown(payload?: Record<string, unknown>): string {
  const structured = structuredArtifactMeta(payload)
  if (structured) return structured.markdown
  const content = payload?.content
  return typeof content === 'string' ? content : ''
}

export type StudyMasteryStatus = 'needs_review' | 'developing' | 'mastered'
export type StudyAdaptationAction = 'prerequisite_detour' | 'schedule_review' | 'extra_practice' | 'slow_pacing'
export type StudyProposalStatus = 'proposed' | 'accepted' | 'dismissed'

export interface StudyMasteryConcept {
  concept_id: string
  unit_id: string | null
  score: number
  status: StudyMasteryStatus
  attempts: number
  last_activity_at: string | null
  lapses: number
}

export interface StudyReviewConsistency {
  reviews: number
  lapses: number
  due_reviews: number
  on_time_rate: number
}

export interface StudyAdaptationProposal {
  schema_version: 1
  proposal_id: string
  concept_id: string | null
  unit_id: string | null
  action: StudyAdaptationAction
  title: string
  rationale: string
  status: StudyProposalStatus
  available: boolean
}

export interface StudyMasteryProjection {
  schema_version: 1
  concepts: StudyMasteryConcept[]
  review_consistency: StudyReviewConsistency
  proposals: StudyAdaptationProposal[]
  generated_at: string
  memory_writes: string[]
}

export type StudyProgressDecision = 'accepted' | 'dismissed'

export interface StudyProgressDecisionInput {
  proposal_id: string
  decision: StudyProgressDecision
  request_id: string
  expected_revision?: number
}

export interface StudyProgressDecisionResponse {
  proposal_id: string
  decision: StudyProgressDecision
  projection: StudyMasteryProjection
}

const ACTIONS = new Set<StudyAdaptationAction>([
  'prerequisite_detour',
  'schedule_review',
  'extra_practice',
  'slow_pacing',
])
const STATUSES = new Set<StudyMasteryStatus>(['needs_review', 'developing', 'mastered'])

function isVisibleText(value: unknown, max = 2_000): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= max && value.trim() === value && !/[\u0000-\u001f\u007f]/.test(value)
}

function isFiniteRatio(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
}

function isAwareIsoTimestamp(value: unknown): value is string {
  return isVisibleText(value, 128) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))
}

/** Strict runtime decoder for API/IPC projections before they reach the UI. */
export function decodeStudyMasteryProjection(value: unknown): StudyMasteryProjection {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid Study progress response')
  const record = value as Record<string, unknown>
  const topKeys = new Set(['schema_version', 'concepts', 'review_consistency', 'proposals', 'generated_at', 'memory_writes'])
  if (Object.keys(record).some((key) => !topKeys.has(key)) || Object.keys(record).length !== topKeys.size || record.schema_version !== 1 || !Array.isArray(record.memory_writes) || record.memory_writes.length !== 0) throw new Error('Invalid Study progress response')
  if (record.memory_writes.some((item) => !isVisibleText(item, 128))) throw new Error('Invalid Study progress response')
  if (!Array.isArray(record.concepts) || record.concepts.length > 500 || !Array.isArray(record.proposals) || record.proposals.length > 100) throw new Error('Invalid Study progress response')
  if (!isAwareIsoTimestamp(record.generated_at)) throw new Error('Invalid Study progress response')
  const consistency = record.review_consistency
  if (!consistency || typeof consistency !== 'object' || Array.isArray(consistency)) throw new Error('Invalid Study progress response')
  const review = consistency as Record<string, unknown>
  if (Object.keys(review).some((key) => !['reviews', 'lapses', 'due_reviews', 'on_time_rate'].includes(key)) || Object.keys(review).length !== 4) throw new Error('Invalid Study progress response')
  if (![review.reviews, review.lapses, review.due_reviews].every((item) => Number.isInteger(item) && (item as number) >= 0 && (item as number) <= 500) || !isFiniteRatio(review.on_time_rate)) throw new Error('Invalid Study progress response')
  const concepts = record.concepts.map((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new Error('Invalid Study progress response')
    const concept = item as Record<string, unknown>
    if (Object.keys(concept).some((key) => !['concept_id', 'unit_id', 'score', 'status', 'attempts', 'last_activity_at', 'lapses'].includes(key)) || Object.keys(concept).length !== 7) throw new Error('Invalid Study progress response')
    if (!isVisibleText(concept.concept_id, 128) || (concept.unit_id !== null && !isVisibleText(concept.unit_id, 64)) || !isFiniteRatio(concept.score) || typeof concept.status !== 'string' || !STATUSES.has(concept.status as StudyMasteryStatus) || !Number.isInteger(concept.attempts) || (concept.attempts as number) < 0 || (concept.attempts as number) > 500 || !Number.isInteger(concept.lapses) || (concept.lapses as number) < 0 || (concept.lapses as number) > 500 || (concept.last_activity_at !== null && !isAwareIsoTimestamp(concept.last_activity_at))) throw new Error('Invalid Study progress response')
    return {
      concept_id: concept.concept_id,
      unit_id: concept.unit_id as string | null,
      score: concept.score,
      status: concept.status as StudyMasteryStatus,
      attempts: concept.attempts as number,
      last_activity_at: concept.last_activity_at as string | null,
      lapses: concept.lapses as number,
    }
  })
  const proposals = record.proposals.map((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new Error('Invalid Study progress response')
    const proposal = item as Record<string, unknown>
    if (Object.keys(proposal).some((key) => !['schema_version', 'proposal_id', 'concept_id', 'unit_id', 'action', 'title', 'rationale', 'status', 'available'].includes(key)) || Object.keys(proposal).length !== 9) throw new Error('Invalid Study progress response')
    if (proposal.schema_version !== 1 || !isVisibleText(proposal.proposal_id, 512) || (proposal.concept_id !== null && !isVisibleText(proposal.concept_id, 128)) || (proposal.unit_id !== null && !isVisibleText(proposal.unit_id, 64)) || typeof proposal.action !== 'string' || !ACTIONS.has(proposal.action as StudyAdaptationAction) || !isVisibleText(proposal.title, 200) || !isVisibleText(proposal.rationale, 2_000) || !['proposed', 'accepted', 'dismissed'].includes(String(proposal.status)) || typeof proposal.available !== 'boolean') throw new Error('Invalid Study progress response')
    return {
      schema_version: 1 as const,
      proposal_id: proposal.proposal_id,
      concept_id: proposal.concept_id as string | null,
      unit_id: proposal.unit_id as string | null,
      action: proposal.action as StudyAdaptationAction,
      title: proposal.title,
      rationale: proposal.rationale,
      status: proposal.status as StudyProposalStatus,
      available: proposal.available,
    }
  })
  return {
    schema_version: 1,
    concepts,
    review_consistency: {
      reviews: review.reviews as number,
      lapses: review.lapses as number,
      due_reviews: review.due_reviews as number,
      on_time_rate: review.on_time_rate as number,
    },
    proposals,
    generated_at: record.generated_at,
    memory_writes: [],
  }
}

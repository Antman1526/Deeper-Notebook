export type StudyRating = 'again' | 'hard' | 'good' | 'easy'

export interface StudyCitation {
  source_id: string
  source_content_sha256: string
  start: number
  end: number
}

export interface StudyCard {
  id: string
  artifact_id: string
  artifact_card_id: string
  version: number
  front: string
  back: string
  citations: StudyCitation[]
  due: string
  stability: number | null
  difficulty: number | null
  lapse_count: number
  current: boolean
}

export interface StudyReviewResult {
  card: StudyCard
  review: {
    id: string | null
    rating: StudyRating
    reviewed_at: string
    lapse_count_after: number
  }
}

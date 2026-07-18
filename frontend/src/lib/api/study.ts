import apiClient from './client'
import type { StudyCard, StudyRating, StudyReviewResult } from '@/lib/types/study'

export const studyApi = {
  listDue: async () => (await apiClient.get<StudyCard[]>('/study/cards/due')).data,
  review: async (cardId: string, rating: StudyRating, requestId: string) =>
    (await apiClient.post<StudyReviewResult>(`/study/cards/${encodeURIComponent(cardId)}/reviews`, {
      rating,
      request_id: requestId,
    })).data,
}

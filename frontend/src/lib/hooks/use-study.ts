import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { QUERY_KEYS } from '@/lib/api/query-client'
import { studyApi } from '@/lib/api/study'
import type { StudyRating } from '@/lib/types/study'

function reviewRequestId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `review-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function useDueStudyCards(enabled = true) {
  return useQuery({ queryKey: QUERY_KEYS.studyDue, queryFn: studyApi.listDue, enabled })
}

export function useReviewStudyCard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ cardId, rating }: { cardId: string; rating: StudyRating }) =>
      studyApi.review(cardId, rating, reviewRequestId()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyDue }),
  })
}

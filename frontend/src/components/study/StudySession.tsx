'use client'

import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useReviewStudyCard } from '@/lib/hooks/use-study'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { StudyCard, StudyRating } from '@/lib/types/study'

interface StudySessionProps {
  cards: StudyCard[]
}

// v0.8.130 — rating colours are status roles from theme tokens: hard = warning,
// good = success, easy = info (UI audit Phase 1).
const RATINGS: Array<{ value: StudyRating; labelKey: string; className: string }> = [
  { value: 'again', labelKey: 'study.studySession.ratings.again', className: 'border-destructive text-destructive hover:bg-destructive/10' },
  { value: 'hard', labelKey: 'study.studySession.ratings.hard', className: 'border-warning text-warning-ink hover:bg-warning-soft' },
  { value: 'good', labelKey: 'study.studySession.ratings.good', className: 'border-success text-success-ink hover:bg-success-soft' },
  { value: 'easy', labelKey: 'study.studySession.ratings.easy', className: 'border-info text-info-ink hover:bg-info-soft' },
]

export function StudySession({ cards }: StudySessionProps) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const review = useReviewStudyCard()
  const card = cards[index]

  useEffect(() => {
    setIndex((current) => Math.min(current, Math.max(cards.length - 1, 0)))
  }, [cards.length])

  if (!card) {
    return <Card><CardContent className="p-6 text-sm text-muted-foreground">{t('study.studySession.nothingDue')}</CardContent></Card>
  }

  const rate = async (rating: StudyRating) => {
    await review.mutateAsync({ cardId: card.id, rating })
    setRevealed(false)
    setIndex((current) => current + 1)
  }

  return (
    <Card aria-label={t('study.studySession.ariaLabel')}>
      <CardHeader className="border-b pb-4">
        <p className="text-xs font-medium text-muted-foreground">{t('study.studySession.cardPosition', { current: index + 1, total: cards.length })}</p>
        <CardTitle className="text-lg">{card.front}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5 p-5">
        {revealed ? (
          <div className="rounded-md border bg-muted/30 p-4 whitespace-pre-wrap text-sm">{card.back}</div>
        ) : (
          <Button type="button" className="w-full" onClick={() => setRevealed(true)}>{t('study.studySession.revealAnswer')}</Button>
        )}
        {revealed ? (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label={t('study.studySession.ratingAriaLabel')}>
            {RATINGS.map((rating) => <Button key={rating.value} type="button" variant="outline" className={rating.className} disabled={review.isPending} onClick={() => void rate(rating.value)}>{t(rating.labelKey)}</Button>)}
          </div>
        ) : null}
        <div className="border-t pt-3 text-xs text-muted-foreground">
          {t('study.studySession.evidence', { sources: card.citations.map((citation) => citation.source_id).join(', ') })}
        </div>
      </CardContent>
    </Card>
  )
}

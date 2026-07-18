'use client'

import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useReviewStudyCard } from '@/lib/hooks/use-study'
import type { StudyCard, StudyRating } from '@/lib/types/study'

interface StudySessionProps {
  cards: StudyCard[]
}

const RATINGS: Array<{ value: StudyRating; label: string; className: string }> = [
  { value: 'again', label: 'Again', className: 'border-destructive text-destructive hover:bg-destructive/10' },
  { value: 'hard', label: 'Hard', className: 'border-amber-500 text-amber-700 hover:bg-amber-500/10' },
  { value: 'good', label: 'Good', className: 'border-emerald-600 text-emerald-700 hover:bg-emerald-600/10' },
  { value: 'easy', label: 'Easy', className: 'border-sky-600 text-sky-700 hover:bg-sky-600/10' },
]

export function StudySession({ cards }: StudySessionProps) {
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const review = useReviewStudyCard()
  const card = cards[index]

  useEffect(() => {
    setIndex((current) => Math.min(current, Math.max(cards.length - 1, 0)))
  }, [cards.length])

  if (!card) {
    return <Card><CardContent className="p-6 text-sm text-muted-foreground">Nothing is due. Your next evidence-backed review will appear here when it is scheduled.</CardContent></Card>
  }

  const rate = async (rating: StudyRating) => {
    await review.mutateAsync({ cardId: card.id, rating })
    setRevealed(false)
    setIndex((current) => current + 1)
  }

  return (
    <Card aria-label="Study session">
      <CardHeader className="border-b pb-4">
        <p className="text-xs font-medium text-muted-foreground">Card {index + 1} of {cards.length}</p>
        <CardTitle className="text-lg">{card.front}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5 p-5">
        {revealed ? (
          <div className="rounded-md border bg-muted/30 p-4 whitespace-pre-wrap text-sm">{card.back}</div>
        ) : (
          <Button type="button" className="w-full" onClick={() => setRevealed(true)}>Reveal answer</Button>
        )}
        {revealed ? (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Review rating">
            {RATINGS.map((rating) => <Button key={rating.value} type="button" variant="outline" className={rating.className} disabled={review.isPending} onClick={() => void rate(rating.value)}>{rating.label}</Button>)}
          </div>
        ) : null}
        <div className="border-t pt-3 text-xs text-muted-foreground">
          Evidence: {card.citations.map((citation) => citation.source_id).join(', ')}
        </div>
      </CardContent>
    </Card>
  )
}

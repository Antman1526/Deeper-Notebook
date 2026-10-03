'use client'

import { BrainCircuit, RotateCcw } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { StudyCard } from '@/lib/types/study'

export function StudyDashboard({ cards }: { cards: StudyCard[] }) {
  const { t } = useTranslation()
  const weakTopics = [...cards]
    .sort((left, right) => right.lapse_count - left.lapse_count)
    .filter((card) => card.lapse_count > 0)
    .slice(0, 3)

  // v0.8.130 — status colours from theme tokens (UI audit Phase 1)
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card>
        <CardHeader className="flex-row items-center gap-2 space-y-0"><BrainCircuit className="h-4 w-4 text-primary" /><CardTitle className="text-sm">{t('study.studyDashboard.dueToday')}</CardTitle></CardHeader>
        <CardContent><p className="text-3xl font-semibold">{cards.length}</p><p className="mt-1 text-xs text-muted-foreground">{t('study.studyDashboard.dueTodayHint')}</p></CardContent>
      </Card>
      <Card>
        <CardHeader className="flex-row items-center gap-2 space-y-0"><RotateCcw className="h-4 w-4 text-warning-ink" /><CardTitle className="text-sm">{t('study.studyDashboard.weakTopics')}</CardTitle></CardHeader>
        <CardContent>
          {weakTopics.length ? <ul className="space-y-1 text-sm">{weakTopics.map((card) => <li key={card.id} className="flex justify-between gap-3"><span className="truncate">{card.artifact_id}</span><span className="text-muted-foreground">{t('study.studyDashboard.lapses', { count: card.lapse_count })}</span></li>)}</ul> : <p className="text-sm text-muted-foreground">{t('study.studyDashboard.noRepeatMisses')}</p>}
        </CardContent>
      </Card>
    </div>
  )
}

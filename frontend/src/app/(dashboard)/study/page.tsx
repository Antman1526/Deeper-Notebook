'use client'

import { AppShell } from '@/components/layout/AppShell'
import { StudyDashboard } from '@/components/study/StudyDashboard'
import { StudySession } from '@/components/study/StudySession'
import { KnowledgeRouteFrame } from '@/components/deeper-notebook/route-frames/KnowledgeRouteFrames'
import { useDueStudyCards } from '@/lib/hooks/use-study'

export default function StudyPage() {
  const due = useDueStudyCards()
  const cards = due.data ?? []

  return (
    <AppShell>
      <KnowledgeRouteFrame
        route="/study"
        description="Review source-grounded cards locally. Scheduling stays on this device."
      >
        <div className="mx-auto max-w-5xl space-y-6">
        {due.isError ? <p role="alert" className="rounded-md border border-destructive/50 p-4 text-sm text-destructive">Study cards could not be loaded. Your existing cards have not been changed.</p> : null}
        <StudyDashboard cards={cards} />
        {due.isLoading ? <p className="text-sm text-muted-foreground">Loading due cards…</p> : <StudySession cards={cards} />}
        </div>
      </KnowledgeRouteFrame>
    </AppShell>
  )
}

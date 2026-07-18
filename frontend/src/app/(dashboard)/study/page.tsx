'use client'

import { AppShell } from '@/components/layout/AppShell'
import { StudyDashboard } from '@/components/study/StudyDashboard'
import { StudySession } from '@/components/study/StudySession'
import { useDueStudyCards } from '@/lib/hooks/use-study'

export default function StudyPage() {
  const due = useDueStudyCards()
  const cards = due.data ?? []

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto"><div className="mx-auto max-w-5xl space-y-6 px-6 py-8 sm:px-8">
        <header><h1 className="text-2xl font-semibold">Study</h1><p className="mt-1 text-sm text-muted-foreground">Review source-grounded cards locally. Scheduling stays on this device.</p></header>
        {due.isError ? <p role="alert" className="rounded-md border border-destructive/50 p-4 text-sm text-destructive">Study cards could not be loaded. Your existing cards have not been changed.</p> : null}
        <StudyDashboard cards={cards} />
        {due.isLoading ? <p className="text-sm text-muted-foreground">Loading due cards…</p> : <StudySession cards={cards} />}
      </div></div>
    </AppShell>
  )
}

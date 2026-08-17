'use client'

import Link from 'next/link'
import { useState } from 'react'

import { ExamLab } from '@/components/study/ExamLab'
import { StudyDashboard } from '@/components/study/StudyDashboard'
import { StudyPlanWizard } from '@/components/study/StudyPlanWizard'
import { StudySession } from '@/components/study/StudySession'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { StudyCard } from '@/lib/types/study'
import { useStudyPlans } from '@/lib/hooks/use-study-plans'

interface StudyWorkbenchProps {
  cards?: StudyCard[]
  cardsLoading?: boolean
  cardsError?: boolean
}

export function StudyWorkbench({ cards = [], cardsLoading = false, cardsError = false }: StudyWorkbenchProps) {
  const [wizardOpen, setWizardOpen] = useState(false)
  const plans = useStudyPlans()
  const activePlans = (plans.data ?? []).filter((plan) => plan.state !== 'archived' && plan.state !== 'completed')

  return (
    <div className="space-y-6" data-study-workbench="enabled">
      <section aria-labelledby="study-plans-heading" className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Study workbench</p>
            <h2 id="study-plans-heading" className="text-2xl font-semibold tracking-tight">Active study plans</h2>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              Keep each learning goal, its approved sources, and the next review in one resumable workspace.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => setWizardOpen(true)}>Create study plan</Button>
            <Button
              type="button"
              variant="outline"
              disabled
              title="Study plan package import is coming in a later release."
            >
              Import study plan
            </Button>
          </div>
        </div>

        {plans.isLoading ? (
          <p role="status" className="rounded-lg border p-5 text-sm text-muted-foreground">Loading study plans…</p>
        ) : plans.isError ? (
          <p role="alert" className="rounded-lg border border-destructive/40 p-5 text-sm text-destructive">
            Study plans could not be loaded. Your existing review cards are unchanged.
          </p>
        ) : activePlans.length === 0 ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Start a focused plan</CardTitle>
              <CardDescription>
                Save your learning goal first; source selection and syllabus review can resume later.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button type="button" variant="outline" onClick={() => setWizardOpen(true)}>Create your first plan</Button>
            </CardContent>
          </Card>
        ) : (
          <ul role="list" className="grid gap-3 md:grid-cols-2">
            {activePlans.map((plan) => (
              <li key={plan.plan_id}>
                <Card className="h-full">
                  <CardHeader>
                    <CardTitle className="truncate text-base">{plan.goal}</CardTitle>
                    <CardDescription>
                      {plan.state.replaceAll('_', ' ')} · {plan.source_links.length} linked {plan.source_links.length === 1 ? 'source' : 'sources'}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Button asChild variant="outline" size="sm">
                      <Link href={`/study/plans/${encodeURIComponent(plan.plan_id)}`}>Open plan</Link>
                    </Button>
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* v0.8.97 — ExamLab: timed exams over Evidence Studio quizzes. */}
      <section aria-labelledby="study-examlab-heading" className="space-y-4">
        <div>
          <h2 id="study-examlab-heading" className="text-lg font-semibold">ExamLab</h2>
          <p className="text-sm text-muted-foreground">
            Timed exam simulation with instant local grading. Misses feed your review deck.
          </p>
        </div>
        <ExamLab />
      </section>

      <section aria-labelledby="study-review-heading" className="space-y-4">
        <div>
          <h2 id="study-review-heading" className="text-lg font-semibold">Today&apos;s review</h2>
          <p className="text-sm text-muted-foreground">Your existing local FSRS session remains available alongside plans.</p>
        </div>
        {cardsError ? (
          <p role="alert" className="rounded-md border border-destructive/50 p-4 text-sm text-destructive">
            Study cards could not be loaded. Your existing cards have not been changed.
          </p>
        ) : null}
        <StudyDashboard cards={cards} />
        {cardsLoading ? <p role="status" className="text-sm text-muted-foreground">Loading due cards…</p> : <StudySession cards={cards} />}
      </section>

      <StudyPlanWizard open={wizardOpen} onOpenChange={setWizardOpen} />
    </div>
  )
}

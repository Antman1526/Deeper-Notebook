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
import { STUDY_PLAN_STATE_KEYS, enumLabel, spacedEnum } from '@/lib/enum-labels'
import { useTranslation } from '@/lib/hooks/use-translation'

interface StudyWorkbenchProps {
  cards?: StudyCard[]
  cardsLoading?: boolean
  cardsError?: boolean
}

export function StudyWorkbench({ cards = [], cardsLoading = false, cardsError = false }: StudyWorkbenchProps) {
  const { t } = useTranslation()
  const [wizardOpen, setWizardOpen] = useState(false)
  const plans = useStudyPlans()
  const activePlans = (plans.data ?? []).filter((plan) => plan.state !== 'archived' && plan.state !== 'completed')

  return (
    <div className="space-y-6" data-study-workbench="enabled">
      <section aria-labelledby="study-plans-heading" className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-medium text-muted-foreground">{t('study.studyWorkbench.eyebrow')}</p>
            <h2 id="study-plans-heading" className="text-2xl font-semibold tracking-tight">{t('study.studyWorkbench.activePlansHeading')}</h2>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              {t('study.studyWorkbench.activePlansDescription')}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => setWizardOpen(true)}>{t('study.studyWorkbench.createPlan')}</Button>
            <Button
              type="button"
              variant="outline"
              disabled
              title={t('study.studyWorkbench.importPlanTitle')}
            >
              {t('study.studyWorkbench.importPlan')}
            </Button>
          </div>
        </div>

        {plans.isLoading ? (
          <p role="status" className="rounded-lg border p-5 text-sm text-muted-foreground">{t('study.studyWorkbench.loadingPlans')}</p>
        ) : plans.isError ? (
          <p role="alert" className="rounded-lg border border-destructive/40 p-5 text-sm text-destructive">
            {t('study.studyWorkbench.plansLoadError')}
          </p>
        ) : activePlans.length === 0 ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('study.studyWorkbench.emptyTitle')}</CardTitle>
              <CardDescription>
                {t('study.studyWorkbench.emptyDescription')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button type="button" variant="outline" onClick={() => setWizardOpen(true)}>{t('study.studyWorkbench.createFirstPlan')}</Button>
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
                      {plan.source_links.length === 1
                        ? t('study.studyWorkbench.planMetaOne', { state: enumLabel(t, STUDY_PLAN_STATE_KEYS, plan.state, spacedEnum(plan.state)), count: plan.source_links.length })
                        : t('study.studyWorkbench.planMetaOther', { state: enumLabel(t, STUDY_PLAN_STATE_KEYS, plan.state, spacedEnum(plan.state)), count: plan.source_links.length })}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Button asChild variant="outline" size="sm">
                      <Link href={`/study/plans/${encodeURIComponent(plan.plan_id)}`}>{t('study.studyWorkbench.openPlan')}</Link>
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
          <h2 id="study-examlab-heading" className="text-lg font-semibold">{t('study.studyWorkbench.examLabHeading')}</h2>
          <p className="text-sm text-muted-foreground">
            {t('study.studyWorkbench.examLabDescription')}
          </p>
        </div>
        <ExamLab />
      </section>

      <section aria-labelledby="study-review-heading" className="space-y-4">
        <div>
          <h2 id="study-review-heading" className="text-lg font-semibold">{t('study.studyWorkbench.reviewHeading')}</h2>
          <p className="text-sm text-muted-foreground">{t('study.studyWorkbench.reviewDescription')}</p>
        </div>
        {cardsError ? (
          <p role="alert" className="rounded-md border border-destructive/50 p-4 text-sm text-destructive">
            {t('study.studyWorkbench.cardsLoadError')}
          </p>
        ) : null}
        <StudyDashboard cards={cards} />
        {cardsLoading ? <p role="status" className="text-sm text-muted-foreground">{t('study.studyWorkbench.loadingCards')}</p> : <StudySession cards={cards} />}
      </section>

      <StudyPlanWizard open={wizardOpen} onOpenChange={setWizardOpen} />
    </div>
  )
}

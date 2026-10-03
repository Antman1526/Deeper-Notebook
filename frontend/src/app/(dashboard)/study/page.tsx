'use client'

import { StudyDashboard } from '@/components/study/StudyDashboard'
import { StudySession } from '@/components/study/StudySession'
import { StudyWorkbench } from '@/components/study/StudyWorkbench'
import { KnowledgeRouteFrame } from '@/components/deeper-notebook/route-frames/KnowledgeRouteFrames'
import { isStudyWorkbenchEnabled } from '@/lib/features'
import { useDueStudyCards } from '@/lib/hooks/use-study'
import { useTranslation } from '@/lib/hooks/use-translation'

export default function StudyPage() {
  const { t } = useTranslation()
  const studyWorkbenchEnabled = isStudyWorkbenchEnabled()
  const due = useDueStudyCards(studyWorkbenchEnabled)
  const cards = due.data ?? []

  return (
    <>
      <KnowledgeRouteFrame
        route="/study"
        description={t('study.studyPage.description')}
      >
        <div className="mx-auto max-w-5xl space-y-6">
          {studyWorkbenchEnabled ? (
            <StudyWorkbench
              cards={cards}
              cardsLoading={due.isLoading}
              cardsError={due.isError}
            />
          ) : (
            <>
              {due.isError ? <p role="alert" className="rounded-md border border-destructive/50 p-4 text-sm text-destructive">{t('study.studyPage.loadError')}</p> : null}
              <StudyDashboard cards={cards} />
              {due.isLoading ? <p className="text-sm text-muted-foreground">{t('study.studyPage.loading')}</p> : <StudySession cards={cards} />}
            </>
          )}
        </div>
      </KnowledgeRouteFrame>
    </>
  )
}

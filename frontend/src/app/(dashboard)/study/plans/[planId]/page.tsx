'use client'

import { useParams } from 'next/navigation'

import { KnowledgeRouteFrame } from '@/components/deeper-notebook/route-frames/KnowledgeRouteFrames'
import { StudyPlanWorkspace } from '@/components/study/StudyPlanWorkspace'
import { isStudyWorkbenchEnabled } from '@/lib/features'
import { useTranslation } from '@/lib/hooks/use-translation'

export default function StudyPlanPage() {
  const { t } = useTranslation()
  const params = useParams<{ planId?: string | string[] }>()
  const rawPlanId = params?.planId
  const planId = Array.isArray(rawPlanId) ? rawPlanId.at(-1) : rawPlanId
  const studyWorkbenchEnabled = isStudyWorkbenchEnabled()

  return (
    <>
      <KnowledgeRouteFrame
        route="/study"
        title={t('study.planIdPage.title')}
        description={t('study.planIdPage.description')}
      >
        <div className="mx-auto w-full max-w-6xl">
          {!studyWorkbenchEnabled ? (
            <div role="status" className="rounded-lg border p-6 text-sm text-muted-foreground">
              {t('study.planIdPage.routeUnavailable')}
            </div>
          ) : planId ? (
            <StudyPlanWorkspace planId={planId} />
          ) : (
            <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/5 p-6 text-sm text-destructive">
              {t('study.planIdPage.planNotIdentified')}
            </div>
          )}
        </div>
      </KnowledgeRouteFrame>
    </>
  )
}

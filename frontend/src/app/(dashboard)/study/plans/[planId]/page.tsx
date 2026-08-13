'use client'

import { useParams } from 'next/navigation'

import { KnowledgeRouteFrame } from '@/components/deeper-notebook/route-frames/KnowledgeRouteFrames'
import { AppShell } from '@/components/layout/AppShell'
import { StudyPlanWorkspace } from '@/components/study/StudyPlanWorkspace'
import { isStudyWorkbenchEnabled } from '@/lib/features'

export default function StudyPlanPage() {
  const params = useParams<{ planId?: string | string[] }>()
  const rawPlanId = params?.planId
  const planId = Array.isArray(rawPlanId) ? rawPlanId.at(-1) : rawPlanId
  const studyWorkbenchEnabled = isStudyWorkbenchEnabled()

  return (
    <AppShell>
      <KnowledgeRouteFrame
        route="/study"
        title="Study"
        description="Review a source-grounded study plan and its explicit syllabus approval boundary."
      >
        <div className="mx-auto w-full max-w-6xl">
          {!studyWorkbenchEnabled ? (
            <div role="status" className="rounded-lg border p-6 text-sm text-muted-foreground">
              This Study plan route is not available in the current release. Return to the Study review surface.
            </div>
          ) : planId ? (
            <StudyPlanWorkspace planId={planId} />
          ) : (
            <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/5 p-6 text-sm text-destructive">
              This study plan could not be identified. Return to Study and choose a plan again.
            </div>
          )}
        </div>
      </KnowledgeRouteFrame>
    </AppShell>
  )
}

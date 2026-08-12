'use client'

import { useParams } from 'next/navigation'

import { KnowledgeRouteFrame } from '@/components/deeper-notebook/route-frames/KnowledgeRouteFrames'
import { AppShell } from '@/components/layout/AppShell'
import { StudyPlanWorkspace } from '@/components/study/StudyPlanWorkspace'

export default function StudyPlanPage() {
  const params = useParams<{ planId?: string | string[] }>()
  const rawPlanId = params?.planId
  const planId = Array.isArray(rawPlanId) ? rawPlanId.at(-1) : rawPlanId

  return (
    <AppShell>
      <KnowledgeRouteFrame
        route="/study"
        title="Study"
        description="Review a source-grounded study plan and its explicit syllabus approval boundary."
      >
        <div className="mx-auto w-full max-w-6xl">
          {planId ? (
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

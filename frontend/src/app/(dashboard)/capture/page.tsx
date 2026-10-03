'use client'

import { CaptureInbox } from '@/components/capture/CaptureInbox'
import { useTranslation } from '@/lib/hooks/use-translation'
import { KnowledgeRouteFrame } from '@/components/deeper-notebook/route-frames/KnowledgeRouteFrames'

export default function CapturePage() {
  const { t } = useTranslation()
  return (
    <>
      <KnowledgeRouteFrame
        route="/capture"
        description={t('capture.capturePage.description')}
      >
        <CaptureInbox />
      </KnowledgeRouteFrame>
    </>
  )
}

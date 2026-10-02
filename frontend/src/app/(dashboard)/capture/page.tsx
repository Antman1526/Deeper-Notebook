'use client'

import { CaptureInbox } from '@/components/capture/CaptureInbox'
import { KnowledgeRouteFrame } from '@/components/deeper-notebook/route-frames/KnowledgeRouteFrames'

export default function CapturePage() {
  return (
    <>
      <KnowledgeRouteFrame
        route="/capture"
        description="Bring local files into your research space without moving or uploading the originals."
      >
        <CaptureInbox />
      </KnowledgeRouteFrame>
    </>
  )
}

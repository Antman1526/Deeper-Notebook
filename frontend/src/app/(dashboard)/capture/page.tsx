'use client'

import { CaptureInbox } from '@/components/capture/CaptureInbox'
import { KnowledgeRouteFrame } from '@/components/deeper-notebook/route-frames/KnowledgeRouteFrames'
import { AppShell } from '@/components/layout/AppShell'

export default function CapturePage() {
  return (
    <AppShell>
      <KnowledgeRouteFrame
        route="/capture"
        description="Bring local files into your research space without moving or uploading the originals."
      >
        <CaptureInbox />
      </KnowledgeRouteFrame>
    </AppShell>
  )
}

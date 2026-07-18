'use client'

import { AppShell } from '@/components/layout/AppShell'
import { CaptureInbox } from '@/components/capture/CaptureInbox'

export default function CapturePage() {
  return <AppShell><div className="flex-1 overflow-y-auto"><div className="mx-auto max-w-5xl px-6 py-8 sm:px-8"><header className="mb-7"><h1 className="text-2xl font-semibold">Capture</h1><p className="mt-1 text-sm text-muted-foreground">Bring local files into your research space without moving or uploading the originals.</p></header><CaptureInbox /></div></div></AppShell>
}

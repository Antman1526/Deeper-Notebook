'use client'

import { AppSidebar } from './AppSidebar'
import { SetupBanner } from './SetupBanner'
import { DbRepairBanner } from './DbRepairBanner'
import { UpdateBanner } from './UpdateBanner'
import { NetworkStatusBadge } from './NetworkStatusBadge'
import { GlobalAudioPlayer } from '@/components/podcasts/GlobalAudioPlayer'
import { GuidedTipsProvider } from '@/components/guided-tips'
import { LuminousAppShell } from '@/components/deeper-notebook/shell/LuminousAppShell'
import { isLuminousFolioEnabled } from '@/lib/features'

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return isLuminousFolioEnabled()
    ? <LuminousAppShell>{children}</LuminousAppShell>
    : <LegacyAppShell>{children}</LegacyAppShell>
}

function LegacyAppShell({ children }: AppShellProps) {
  return (
    <div className="flex h-screen overflow-hidden">
      <AppSidebar />
      <main className="flex-1 flex flex-col min-h-0 overflow-hidden">
        <SetupBanner />
        <DbRepairBanner />
        <UpdateBanner />
        <NetworkStatusBadge />
        {children}
        <GuidedTipsProvider />
        <GlobalAudioPlayer />
      </main>
    </div>
  )
}

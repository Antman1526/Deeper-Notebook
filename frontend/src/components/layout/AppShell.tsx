'use client'

import { AppSidebar } from './AppSidebar'
import { SetupBanner } from './SetupBanner'
import { DbRepairBanner } from './DbRepairBanner'
import { UpdateBanner } from './UpdateBanner'
import { NetworkStatusBadge } from './NetworkStatusBadge'
import { GlobalAudioPlayer } from '@/components/podcasts/GlobalAudioPlayer'

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex h-screen overflow-hidden">
      <AppSidebar />
      <main className="flex-1 flex flex-col min-h-0 overflow-hidden">
        <SetupBanner />
        <DbRepairBanner />
        <UpdateBanner />
        <NetworkStatusBadge />
        {children}
        <GlobalAudioPlayer />
      </main>
    </div>
  )
}

'use client'

import { GuidedTipsProvider } from '@/components/guided-tips'
import { DbRepairBanner } from '@/components/layout/DbRepairBanner'
import { NetworkStatusBadge } from '@/components/layout/NetworkStatusBadge'
import { SetupBanner } from '@/components/layout/SetupBanner'
import { UpdateBanner } from '@/components/layout/UpdateBanner'
import { GlobalAudioPlayer } from '@/components/podcasts/GlobalAudioPlayer'

/**
 * The utility layer deliberately composes the existing implementations. It
 * owns placement only; banner, guided-tip, and audio behavior stay in their
 * current modules so the legacy shell and the Luminous shell share one truth.
 */
export function ShellUtilities() {
  return (
    <div className="dn-shell-utilities">
      <div className="dn-shell-banners">
        <SetupBanner />
        <DbRepairBanner />
        <UpdateBanner />
        <NetworkStatusBadge />
      </div>
      <GuidedTipsProvider />
      <div data-testid="global-audio-player" className="dn-shell-audio">
        <GlobalAudioPlayer />
      </div>
    </div>
  )
}

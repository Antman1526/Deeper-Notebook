'use client'

import { WifiOff } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useNetworkStatus } from '@/lib/hooks/use-network-status'

// v0.8.68 — persistent offline indicator (spec §4). Renders nothing while
// online/unknown. Two copies: real offline ("answering with <local model>")
// vs the user's own Offline-mode toggle. Informational, not dismissible —
// it self-clears when connectivity returns (the hook keeps polling).
export function NetworkStatusBadge() {
  const { t } = useTranslation()
  const { data } = useNetworkStatus()

  if (!data || data.status !== 'offline') return null

  const label = data.forced_offline
    ? t('network.forcedOffline', { defaultValue: 'Offline mode on' })
    : data.local_fallback_model
      ? t('network.offlineWithFallback', {
          defaultValue: 'Offline — answering with {{model}}',
          model: data.local_fallback_model,
        })
      : t('network.offline', { defaultValue: 'Offline — local features only' })

  return (
    <div className="px-4 pt-2">
      <div
        className="flex items-center gap-2 rounded-md border border-amber-500/50 bg-amber-500/10 px-3 py-1.5 text-sm text-amber-700 dark:text-amber-400"
        data-testid="network-status-badge"
      >
        <WifiOff className="h-4 w-4 shrink-0" />
        <span>{label}</span>
      </div>
    </div>
  )
}

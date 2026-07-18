'use client'

import { useLocalModelsHealth } from '@/lib/hooks/use-local-models'
import { useTranslation } from '@/lib/hooks/use-translation'
// v0.8.38 — click a red badge → log popover with classified failure hint
import { SidecarLogPopover, sidecarKindFromName } from './SidecarLogPopover'

// Phase 1 — traffic-light dots so the user can see at-a-glance
// which sidecars are reachable. Mapped to Tailwind tokens so
// the colors adapt to the active theme (light / dark / ONP
// custom palettes).
//
// v0.8.0 — Status keys for i18n (used via template literal in render).
// Keys: models.status.healthy, models.status.unhealthy, models.status.notConfigured,
// models.status.unknown, models.status.noDetail
const STATUS_DOT: Record<string, string> = {
  healthy: 'bg-emerald-500',
  unhealthy: 'bg-rose-500',
  // v0.8.0 — /60 calculated to ~2.84:1 contrast on dark mode; bumped to /70 for WCAG AA 3:1 (non-text graphical object).
  not_configured: 'bg-muted-foreground/70',
  unknown: 'bg-amber-500',
}

export function LocalModelHealthBadges() {
  const { data, isLoading } = useLocalModelsHealth()
  const { t } = useTranslation()
  // Hidden during the initial fetch + on outright endpoint
  // failure. Better than showing a permanent "unknown" state
  // that the user can't action on.
  if (isLoading || !data) return null
  return (
    <div className="space-y-1 text-[10px]">
      {data.models.map((m) => {
        // v0.8.38 — only the unhealthy dot is interactive. Healthy +
        // not_configured + unknown dots stay static; popping a log on
        // "everything's fine" would just confuse the user.
        const kind = m.status === 'unhealthy' ? sidecarKindFromName(m.name) : null
        const dot = (
          <span
            className={`h-2 w-2 rounded-full ${STATUS_DOT[m.status] ?? STATUS_DOT.unknown} ${kind ? 'cursor-pointer ring-offset-1 hover:ring-2 hover:ring-rose-300' : ''}`}
            title={`${t(`models.status.${m.status}`)}: ${m.detail ?? t('models.status.noDetail')}`}
            aria-label={`${m.name}: ${t(`models.status.${m.status}`)}`}
            role={kind ? 'button' : undefined}
            tabIndex={kind ? 0 : undefined}
          />
        )
        return (
          <div key={m.name} className="flex items-center gap-1.5">
            {/* v0.8.0 — i18n: status strings translated per frontend convention (was hardcoded EN) */}
            {/* v0.8.38 — wrap unhealthy dots in a popover; static otherwise. */}
            {kind ? (
              <SidecarLogPopover kind={kind}>{dot}</SidecarLogPopover>
            ) : (
              dot
            )}
            <span className="truncate text-muted-foreground">{m.name}</span>
          </div>
        )
      })}
    </div>
  )
}


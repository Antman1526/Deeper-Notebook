'use client'

import { useLocalModelsHealth } from '@/lib/hooks/use-local-models'

// Phase 1 — traffic-light dots so the user can see at-a-glance
// which sidecars are reachable. Mapped to Tailwind tokens so
// the colors adapt to the active theme (light / dark / 9 ONP
// custom palettes).
const STATUS_DOT: Record<string, string> = {
  healthy: 'bg-emerald-500',
  unhealthy: 'bg-rose-500',
  not_configured: 'bg-muted-foreground/40',
  unknown: 'bg-amber-500',
}

export function LocalModelHealthBadges() {
  const { data, isLoading } = useLocalModelsHealth()
  // Hidden during the initial fetch + on outright endpoint
  // failure. Better than showing a permanent "unknown" state
  // that the user can't action on.
  if (isLoading || !data) return null
  return (
    <div className="space-y-1 text-[10px]">
      {data.models.map((m) => (
        <div key={m.name} className="flex items-center gap-1.5">
          <span
            className={`h-2 w-2 rounded-full ${STATUS_DOT[m.status] ?? STATUS_DOT.unknown}`}
            title={`${m.status}: ${m.detail ?? ''}`}
            aria-label={`${m.name}: ${m.status}`}
          />
          <span className="truncate text-muted-foreground">{m.name}</span>
        </div>
      ))}
    </div>
  )
}

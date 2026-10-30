'use client'

import { Kbd } from '@/components/ui/kbd'
import { useIsMac } from '@/lib/hooks/use-is-mac'

// v0.8.130 — the platform-correct palette shortcut for prose tips, which printed
// both ("⌘K / Ctrl+K"). Renders nothing until the platform is known, so the server
// and first client render agree.
export function CommandPaletteKey() {
  const isMac = useIsMac()
  if (isMac === null) return null
  return <Kbd>{isMac ? '⌘K' : 'Ctrl+K'}</Kbd>
}

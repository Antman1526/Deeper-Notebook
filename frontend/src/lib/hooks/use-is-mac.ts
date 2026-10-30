'use client'

import { useEffect, useState } from 'react'

interface PlatformSource {
  platform?: string
  userAgentData?: { platform?: string }
}

/**
 * v0.8.130 — Whether the browser is running on macOS. Prefers the UA client-hints platform,
 * which replaces the deprecated `navigator.platform`, and falls back to it.
 */
export function detectMac(source: PlatformSource = navigator as PlatformSource): boolean {
  const platform = source.userAgentData?.platform || source.platform || ''
  return /mac/i.test(platform)
}

/**
 * `true` on macOS, `false` elsewhere, `null` until the client has mounted.
 * Callers render no shortcut hint while it is `null` instead of guessing, so
 * the server render and the first client paint agree.
 */
export function useIsMac(): boolean | null {
  const [isMac, setIsMac] = useState<boolean | null>(null)

  useEffect(() => {
    setIsMac(detectMac())
  }, [])

  return isMac
}

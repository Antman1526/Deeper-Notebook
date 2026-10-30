'use client'

import { useEffect, useState } from 'react'

import { readDesktopVersion } from '@/lib/desktop-version'

/**
 * v0.8.130 — Only the packaged desktop app exposes a version; in a plain browser this
 * stays ''. The desktop shell injects the value from its `loaded` handler, after React
 * has hydrated, so a single read at mount would miss it: look again for a few seconds.
 * (Moved out of InstrumentDock so the V2 rail shares it.)
 */
export function useDesktopVersion(): string {
  const [version, setVersion] = useState('')
  useEffect(() => {
    const read = () => {
      const found = readDesktopVersion(window)
      if (found) setVersion(found)
      return Boolean(found)
    }
    if (read()) return undefined

    let attempts = 0
    const timer = window.setInterval(() => {
      attempts += 1
      if (read() || attempts >= 40) window.clearInterval(timer)
    }, 500)
    return () => window.clearInterval(timer)
  }, [])
  return version
}

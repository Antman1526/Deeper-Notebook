'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { ConnectionError } from '@/lib/types/config'
import { ConnectionErrorOverlay } from '@/components/errors/ConnectionErrorOverlay'
import { getConfig, resetConfig } from '@/lib/config'

interface ConnectionGuardProps {
  children: React.ReactNode
}

export function ConnectionGuard({ children }: ConnectionGuardProps) {
  const [error, setError] = useState<ConnectionError | null>(null)
  const [isChecking, setIsChecking] = useState(true)
  // Use a ref to track checking status to avoid dependency cycles
  const isCheckingRef = useRef(false)

  const checkConnection = useCallback(async () => {
    // Prevent re-entry if already checking
    if (isCheckingRef.current) {
       return
    }

    isCheckingRef.current = true
    setIsChecking(true)
    setError(null)

    // v0.8.71 — retry through the cold-boot startup race before surfacing an
    // error. On a fresh desktop launch the Next `/api/config` proxy can briefly
    // return ECONNREFUSED (the dynamic API port isn't listening yet, so the
    // proxy falls back to localhost:5055), and the DB can momentarily report
    // `offline` while migrations finish. The previous single-shot check latched
    // the full-screen ConnectionErrorOverlay ("reload error on startup") even
    // though the backend came up a beat later. Poll a handful of times with a
    // short backoff; only show the overlay once the backend is genuinely
    // unreachable. The user-triggered Retry path reuses this same loop.
    const MAX_ATTEMPTS = 10
    const DELAY_MS = 600
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

    let lastError: unknown = null
    let dbOfflineUrl: string | undefined

    for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
      // Force a fresh fetch each attempt (clears the cached/rejected promise).
      resetConfig()
      try {
        const config = await getConfig()

        if (config.dbStatus === 'offline') {
          // Give the DB a few beats to finish migrations on a cold boot before
          // treating "offline" as a real failure.
          dbOfflineUrl = config.apiUrl
          if (attempt < MAX_ATTEMPTS - 1) {
            await sleep(DELAY_MS)
            continue
          }
          setError({
            type: 'database-offline',
            details: { message: 'Database is offline', attemptedUrl: dbOfflineUrl },
          })
          break
        }

        // Connection is good.
        setError(null)
        isCheckingRef.current = false
        setIsChecking(false)
        return
      } catch (err) {
        lastError = err
        if (attempt < MAX_ATTEMPTS - 1) {
          await sleep(DELAY_MS)
          continue
        }
      }
    }

    // Exhausted retries with the API unreachable.
    if (lastError) {
      const errorMessage = lastError instanceof Error ? lastError.message : 'Unknown error'
      const attemptedUrl =
        typeof window !== 'undefined'
          ? `${window.location.origin}/api/config`
          : undefined
      setError({
        type: 'api-unreachable',
        details: {
          message: 'Unable to connect to API',
          technicalMessage: errorMessage,
          stack: lastError instanceof Error ? lastError.stack : undefined,
          attemptedUrl,
        },
      })
    }

    isCheckingRef.current = false
    setIsChecking(false)
  }, []) // Empty dependency array - stable callback

  // Check connection on mount
  useEffect(() => {
    checkConnection()
  }, [checkConnection])

  // Add keyboard shortcut for retry (R key)
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      // v0.8.66 (audit F-6) — guard the global "R" shortcut so it doesn't
      // hijack Cmd/Ctrl+R (reload), key-repeat, or typing in an input. Matches
      // the project's own CommandPalette convention.
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return
      const target = e.target as HTMLElement | null
      const tag = target?.tagName
      if (
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        target?.isContentEditable
      ) {
        return
      }
      if (error && (e.key === 'r' || e.key === 'R')) {
        e.preventDefault()
        checkConnection()
      }
    }

    window.addEventListener('keydown', handleKeyPress)
    return () => window.removeEventListener('keydown', handleKeyPress)
  }, [error, checkConnection])

  // Show overlay if there's an error
  if (error) {
    return <ConnectionErrorOverlay error={error} onRetry={checkConnection} />
  }

  // v0.8.71 — while checking (incl. the retry window above), show a quiet
  // themed "Connecting…" instead of a blank screen. The spin is auto-zeroed
  // under prefers-reduced-motion by the global rule in globals.css.
  if (isChecking) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary/30 border-t-primary" />
          <span className="text-sm">Connecting…</span>
        </div>
      </div>
    )
  }

  // Render children if connection is good
  return <>{children}</>
}

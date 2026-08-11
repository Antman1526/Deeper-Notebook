'use client'

import { Copy, RefreshCw, RotateCw } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { FolioState } from '@/components/deeper-notebook/folio/FolioState'

const DIAGNOSTIC_CODE = 'DN-UI-RECOVERY'

interface RelaunchWindow {
  DN?: { relaunch?: () => boolean }
  ONP?: { relaunch?: () => boolean }
}

export interface RecoveryCenterProps {
  resetError: () => void
  /** Accepted for ErrorBoundary/custom-fallback compatibility; never rendered. */
  error?: Error
}

function getRelaunch(): (() => boolean) | undefined {
  if (typeof window === 'undefined') return undefined
  const candidate = window as unknown as Window & RelaunchWindow
  return candidate.DN?.relaunch ?? candidate.ONP?.relaunch
}

export function RecoveryCenter({ resetError }: RecoveryCenterProps) {
  const [copyState, setCopyState] = React.useState<'idle' | 'copied' | 'unavailable'>('idle')
  const [relaunchUnavailable, setRelaunchUnavailable] = React.useState(false)
  const relaunch = getRelaunch()

  const copyDiagnostic = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
      await navigator.clipboard.writeText(DIAGNOSTIC_CODE)
      setCopyState('copied')
    } catch {
      setCopyState('unavailable')
    }
  }

  const relaunchDesktop = () => {
    try {
      if (!relaunch || relaunch() === false) setRelaunchUnavailable(true)
    } catch {
      setRelaunchUnavailable(true)
    }
  }

  return (
    <div className="motion-reduce:transition-none">
      <FolioState
        kind="error"
        title="Recovery Center"
        description="This view could not be rendered. Your local data was not changed. Try the view again or reload the page."
        action={
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={resetError}>
              <RefreshCw aria-hidden="true" className="mr-2 h-4 w-4" />
              Try again
            </Button>
            <Button type="button" onClick={() => window.location.reload()}>
              Reload page
            </Button>
            <Button type="button" variant="ghost" onClick={() => void copyDiagnostic()}>
              <Copy aria-hidden="true" className="mr-2 h-4 w-4" />
              Copy diagnostic code
            </Button>
            {relaunch ? (
              <Button type="button" variant="ghost" onClick={relaunchDesktop}>
                <RotateCw aria-hidden="true" className="mr-2 h-4 w-4" />
                Relaunch desktop app
              </Button>
            ) : null}
          </div>
        }
      />
      <p role="status" aria-live="polite" className="mt-3 text-sm text-muted-foreground">
        {copyState === 'copied'
          ? 'Diagnostic code copied'
          : copyState === 'unavailable'
            ? 'Copy unavailable'
            : relaunchUnavailable
              ? 'Desktop relaunch unavailable'
              : 'Diagnostic code: DN-UI-RECOVERY'}
      </p>
    </div>
  )
}

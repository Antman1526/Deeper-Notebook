'use client'

import { Copy, RefreshCw, RotateCw } from 'lucide-react'
import * as React from 'react'

import { Button } from '@/components/ui/button'
import { FolioState } from '@/components/deeper-notebook/folio/FolioState'
import { useTranslation } from '@/lib/hooks/use-translation'

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
  const { t } = useTranslation()
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
        title={t('common.recoveryCenter.title')}
        description={t('common.recoveryCenter.description')}
        action={
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={resetError}>
              <RefreshCw aria-hidden="true" className="mr-2 h-4 w-4" />
              {t('common.retry')}
            </Button>
            <Button type="button" onClick={() => window.location.reload()}>
              {t('common.recoveryCenter.reloadPage')}
            </Button>
            <Button type="button" variant="ghost" onClick={() => void copyDiagnostic()}>
              <Copy aria-hidden="true" className="mr-2 h-4 w-4" />
              {t('common.recoveryCenter.copyDiagnosticCode')}
            </Button>
            {relaunch ? (
              <Button type="button" variant="ghost" onClick={relaunchDesktop}>
                <RotateCw aria-hidden="true" className="mr-2 h-4 w-4" />
                {t('common.recoveryCenter.relaunchDesktopApp')}
              </Button>
            ) : null}
          </div>
        }
      />
      <p role="status" aria-live="polite" className="mt-3 text-sm text-muted-foreground">
        {copyState === 'copied'
          ? t('common.recoveryCenter.diagnosticCodeCopied')
          : copyState === 'unavailable'
            ? t('common.recoveryCenter.copyUnavailable')
            : relaunchUnavailable
              ? t('common.recoveryCenter.relaunchUnavailable')
              : t('common.recoveryCenter.diagnosticCode', { code: DIAGNOSTIC_CODE })}
      </p>
    </div>
  )
}

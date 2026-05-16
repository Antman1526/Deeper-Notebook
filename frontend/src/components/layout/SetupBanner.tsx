'use client'

import { useMemo } from 'react'
import Link from 'next/link'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ShieldAlert, AlertTriangle, ArrowRight, ExternalLink } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useCredentialStatus, useEnvStatus } from '@/lib/hooks/use-credentials'

export function SetupBanner() {
  const { t } = useTranslation()
  const { data: credentialStatus } = useCredentialStatus()
  const { data: envStatus } = useEnvStatus()

  const encryptionReady = credentialStatus?.encryption_configured ?? true

  const providersToMigrate = useMemo(() => {
    if (!envStatus || !credentialStatus) return []
    const providers: string[] = []
    for (const provider in envStatus) {
      if (envStatus[provider] && credentialStatus.source[provider] === 'environment') {
        providers.push(provider)
      }
    }
    return providers
  }, [envStatus, credentialStatus])

  if (encryptionReady && providersToMigrate.length === 0) {
    return null
  }

  // v0.7.25 — was hardcoded `red-50` / `amber-50` / `red-800` etc.,
  // which bypass the 9-theme token system entirely. Under any
  // non-default theme the alert flips back to stock red/amber and
  // looks foreign. Switched the critical case to `destructive`
  // semantic tokens. For the warning case we add proper light/dark
  // bg with theme-aware contrast (no semantic `--warning` token
  // exists yet — added separately in v0.7.27 design pass).
  if (!encryptionReady) {
    return (
      <div className="px-4 pt-3">
        <Alert className="border-destructive/50 bg-destructive/10 text-destructive">
          <ShieldAlert className="h-4 w-4" />
          <AlertTitle>
            {t('setupBanner.encryptionRequired')}
          </AlertTitle>
          <AlertDescription className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span>{t('setupBanner.encryptionRequiredDescription')}</span>
            <a
              href="https://github.com/lfnovo/open-notebook/blob/main/docs/3-USER-GUIDE/api-configuration.md#encryption-setup"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center shrink-0 text-sm font-medium underline underline-offset-2 hover:opacity-80"
            >
              {t('setupBanner.viewDocs')}
              <ExternalLink className="ml-1 h-3 w-3" />
            </a>
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="px-4 pt-3">
      <Alert className="border-amber-500/50 bg-amber-100/40 text-amber-900 dark:bg-amber-900/20 dark:text-amber-100">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>
          {t('setupBanner.migrationAvailable')}
        </AlertTitle>
        <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span>
            {t('setupBanner.migrationDescription').replace('{count}', providersToMigrate.length.toString())}
          </span>
          <Button
            variant="outline"
            size="sm"
            asChild
            className="shrink-0"
          >
            <Link href="/settings/api-keys">
              {t('setupBanner.goToSettings')}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </AlertDescription>
      </Alert>
    </div>
  )
}

'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  ShieldAlert,
  AlertTriangle,
  ArrowRight,
  ExternalLink,
  X,
} from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useCredentialStatus, useEnvStatus } from '@/lib/hooks/use-credentials'
import { useDeepHealth } from '@/lib/hooks/use-deep-health'

// v0.7.117 — session-only dismissal of the deep-health banner so a
// user who's already aware of a degraded subsystem isn't nagged on
// every page. State lives outside the component so the dismissal
// survives route changes within the same session but is cleared on
// reload (no localStorage on purpose).
let _deepHealthBannerDismissed = false

export function SetupBanner() {
  const { t } = useTranslation()
  const pathname = usePathname()
  const { data: credentialStatus } = useCredentialStatus()
  const { data: envStatus } = useEnvStatus()
  const { data: deepHealth } = useDeepHealth()
  const [, forceRender] = useState(0)

  const encryptionReady = credentialStatus?.encryption_configured ?? true

  const providersToMigrate = useMemo(() => {
    if (!envStatus || !credentialStatus) return []
    const providers: string[] = []
    const credentialSources = credentialStatus.source ?? {}
    for (const provider in envStatus) {
      if (envStatus[provider] && credentialSources[provider] === 'environment') {
        providers.push(provider)
      }
    }
    return providers
  }, [envStatus, credentialStatus])

  // v0.7.117 — hide the deep-health banner on the wizard route itself
  // (the wizard already shows the full per-subsystem breakdown; a
  // redundant banner would be noise).
  const onWizardRoute = pathname === '/setup-wizard'
  const showDeepHealthBanner =
    !onWizardRoute &&
    !_deepHealthBannerDismissed &&
    deepHealth !== undefined &&
    deepHealth.status !== 'healthy'

  if (encryptionReady && providersToMigrate.length === 0 && !showDeepHealthBanner) {
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
            {/* v0.7.201 — point at the Plus fork (Antman1526/
                open-notebook-Plus) instead of the upstream lfnovo
                repo. The fork's docs branch + path layout may drift
                from upstream; keeping the link inside the Plus repo
                ensures users land on docs that match the build
                they're running. */}
            <a
              href="https://github.com/Antman1526/open-notebook-Plus/blob/main/docs/3-USER-GUIDE/api-configuration.md#encryption-setup"
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

  // v0.7.117 — degraded subsystem(s) detected via /healthz/deep. Takes
  // precedence over the API-key migration banner because a broken
  // embedding model or chat model blocks core flows entirely while
  // env→DB migration is just an ergonomics win.
  if (showDeepHealthBanner) {
    return (
      <div className="px-4 pt-3" data-testid="deep-health-banner">
        <Alert className="border-warning/50 bg-warning/10 text-warning-foreground">
          <AlertTriangle className="h-4 w-4 text-warning" />
          <AlertTitle>{t('setupBanner.degraded')}</AlertTitle>
          <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>{t('setupBanner.degradedDescription')}</span>
            <div className="flex items-center gap-2 shrink-0">
              <Button variant="outline" size="sm" asChild>
                <Link href="/setup-wizard">
                  {t('setupBanner.openWizard')}
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                aria-label={t('setupBanner.dismiss')}
                onClick={() => {
                  _deepHealthBannerDismissed = true
                  forceRender((n) => n + 1)
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  // v0.7.27 — uses the new --warning semantic token from globals.css.
  // text-warning-foreground falls back to a high-contrast text per theme;
  // border-warning/50 gives the right strength regardless of theme.
  return (
    <div className="px-4 pt-3">
      <Alert className="border-warning/50 bg-warning/10 text-warning-foreground">
        <AlertTriangle className="h-4 w-4 text-warning" />
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

// v0.7.117 — exported for tests to reset session-only dismissal state.
export function __resetDeepHealthBannerDismissed() {
  _deepHealthBannerDismissed = false
}

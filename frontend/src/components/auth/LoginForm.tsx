'use client'

import { useState, useEffect, useId, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/hooks/use-auth'
import { useAuthStore } from '@/lib/stores/auth-store'
import { getConfig } from '@/lib/config'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AlertCircle, ChevronRight, Eye, EyeOff } from 'lucide-react'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { useTranslation } from '@/lib/hooks/use-translation'
import { formatDateTime } from '@/lib/utils/date-locale'

type LoginFormProps = {
  /** Inside the V2 auth frame, which owns the brand, the heading and the description. */
  embedded?: boolean
}

// v0.8.130 — Phase 3c: embedded, the form drops its own card, full-screen wrapper and
// "Deeper Notebook" heading (the login said the name three times). The legacy
// AuthFolio route keeps the card.
function Surface({ embedded, header, children }: { embedded: boolean; header: ReactNode; children: ReactNode }) {
  if (embedded) {
    return (
      <div className="space-y-4">
        {header}
        {children}
      </div>
    )
  }
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">{header}</CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </div>
  )
}

export function LoginForm({ embedded = false }: LoginFormProps) {
  const { t, language } = useTranslation()
  const [password, setPassword] = useState('')
  // v0.7.198 — show/hide toggle. Standard password-field affordance;
  // lets users verify what they typed (especially helpful on touch
  // devices where typos are more frequent). Toggled state is per-
  // render only; no persistence (cleared on remount).
  const [showPassword, setShowPassword] = useState(false)
  const passwordId = useId()
  const { login, isLoading, error } = useAuth()
  const { authRequired, checkAuthRequired, hasHydrated, isAuthenticated } = useAuthStore()
  const [isCheckingAuth, setIsCheckingAuth] = useState(true)
  const [configInfo, setConfigInfo] = useState<{ apiUrl: string; version: string; buildTime: string } | null>(null)
  const router = useRouter()

  // Load config info for debugging
  useEffect(() => {
    getConfig().then(cfg => {
      setConfigInfo({
        apiUrl: cfg.apiUrl,
        version: cfg.version,
        buildTime: cfg.buildTime,
      })
    }).catch(err => {
      console.error('Failed to load config:', err)
    })
  }, [])

  // Check if authentication is required on mount
  useEffect(() => {
    if (!hasHydrated) {
      return
    }

    const checkAuth = async () => {
      try {
        const required = await checkAuthRequired()

        // If auth is not required, redirect to notebooks
        if (!required) {
          router.push('/notebooks')
        }
      } catch (error) {
        console.error('Error checking auth requirement:', error)
        // On error, assume auth is required to be safe
      } finally {
        setIsCheckingAuth(false)
      }
    }

    // If we already know auth status, use it
    if (authRequired !== null) {
      if (!authRequired && isAuthenticated) {
        router.push('/notebooks')
      } else {
        setIsCheckingAuth(false)
      }
    } else {
      void checkAuth()
    }
  }, [hasHydrated, authRequired, checkAuthRequired, router, isAuthenticated])

  // Show loading while checking if auth is required
  if (!hasHydrated || isCheckingAuth) {
    return (
      <div className={embedded ? 'flex justify-center py-12' : 'min-h-screen flex items-center justify-center bg-background'}>
        <LoadingSpinner />
      </div>
    )
  }

  // If we still don't know if auth is required (connection error), show error
  if (authRequired === null) {
    return (
      <Surface
        embedded={embedded}
        header={embedded ? (
          <div>
            <p className="font-medium">{t('common.connectionError')}</p>
            <p className="text-sm text-muted-foreground">{t('common.unableToConnect')}</p>
          </div>
        ) : (
          <>
            <CardTitle>{t('common.connectionError')}</CardTitle>
            <CardDescription>
              {t('common.unableToConnect')}
            </CardDescription>
          </>
        )}
      >
            <div className="space-y-4">
              <div className="flex items-start gap-2 text-destructive text-sm">
                <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  {error || t('auth.connectErrorHint')}
                </div>
              </div>

              {configInfo && (
                <div className="space-y-2 text-xs text-muted-foreground border-t pt-3">
                  <div className="font-medium">{t('common.diagnosticInfo')}:</div>
                  <div className="space-y-1 font-mono">
                    <div>{t('common.version')}: {configInfo.version}</div>
                    <div>{t('common.built')}: {formatDateTime(configInfo.buildTime, language)}</div>
                    <div className="break-all">{t('common.apiUrl')}: {configInfo.apiUrl}</div>
                    <div className="break-all">{t('common.frontendUrl')}: {typeof window !== 'undefined' ? window.location.href : 'N/A'}</div>
                  </div>
                  <div className="text-xs pt-2">
                    {t('common.checkConsoleLogs')}
                  </div>
                </div>
              )}

              <Button
                onClick={() => window.location.reload()}
                className="w-full"
              >
                {t('common.retryConnection')}
              </Button>
            </div>
      </Surface>
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password.trim()) {
      try {
        await login(password)
      } catch (error) {
        console.error('Unhandled error during login:', error)
        // The auth store should handle most errors, but this catches any unhandled ones
      }
    }
  }

  return (
    <Surface
      embedded={embedded}
      header={embedded ? null : (
        <>
          <h1 className="leading-none font-semibold">{t('auth.loginTitle')}</h1>
          <CardDescription>
            {t('auth.loginDesc')}
          </CardDescription>
        </>
      )}
    >
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* v0.8.130 — a real label (visible when embedded, screen-reader only on the
                legacy card) and autocomplete, so password managers fill the field. */}
            <Label htmlFor={passwordId} className={embedded ? undefined : 'sr-only'}>
              {t('auth.passwordPlaceholder')}
            </Label>
            {/* v0.7.198 — show/hide affordance. Relative wrapper so
                the eye toggle absolute-positions inside the input. */}
            <div className="relative">
              <Input
                id={passwordId}
                autoComplete="current-password"
                type={showPassword ? 'text' : 'password'}
                // Embedded, the visible label already says "Password".
                placeholder={embedded ? undefined : t('auth.passwordPlaceholder')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword(v => !v)}
                disabled={isLoading}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                aria-pressed={showPassword}
                className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:text-foreground disabled:opacity-50"
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <Eye className="h-4 w-4" aria-hidden="true" />
                )}
              </button>
            </div>

            {error && (
              <div role="alert" className="flex items-center gap-2 text-destructive text-sm">
                <AlertCircle className="h-4 w-4" />
                {error}
              </div>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={isLoading || !password.trim()}
            >
              {isLoading ? t('auth.signingIn') : t('auth.signIn')}
            </Button>

            {/* v0.8.130 — Phase 3c: embedded, the version and API address are debug
                details, so they sit behind a disclosure instead of a footer. */}
            {configInfo && embedded ? (
              <details className="group text-xs text-muted-foreground">
                {/* role="button": Chromium exposes a bare summary with no action role. */}
                <summary role="button" className="inline-flex min-h-11 cursor-pointer select-none items-center gap-1">
                  {/* inline-flex drops the native marker; the chevron replaces it. */}
                  <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" aria-hidden="true" />
                  {t('auth.connectionDetails')}
                </summary>
                <div className="mt-2 space-y-1">
                  <div>{t('common.version')} {configInfo.version}</div>
                  {configInfo.apiUrl ? <div className="font-mono break-all">{configInfo.apiUrl}</div> : null}
                </div>
              </details>
            ) : configInfo ? (
              <div className="text-xs text-center text-muted-foreground pt-2 border-t">
                <div>{t('common.version')} {configInfo.version}</div>
                {/* v0.8.130 — 12px type floor (UI audit Phase 1) */}
                <div className="font-mono text-xs">{configInfo.apiUrl}</div>
              </div>
            ) : null}
          </form>
    </Surface>
  )
}

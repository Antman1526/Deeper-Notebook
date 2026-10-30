'use client'

import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { AlertTriangle, ArrowRight, Loader2 } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useMigrateFromEnv } from '@/lib/hooks/use-credentials'

interface MigrationBannerProps {
  providersToMigrate: string[]
}

export function MigrationBanner({ providersToMigrate }: MigrationBannerProps) {
  const { t } = useTranslation()
  const migrate = useMigrateFromEnv()

  if (providersToMigrate.length === 0) {
    return null
  }

  return (
    // v0.8.130 — status colours from the Alert warning variant (UI audit Phase 1)
    <Alert variant="warning">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>
        {t('apiKeys.migrationAvailable')}
      </AlertTitle>
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span>
          {t('apiKeys.migrationDescription').replace('{count}', providersToMigrate.length.toString())}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => migrate.mutate()}
          disabled={migrate.isPending}
          className="shrink-0 border-warning/40 text-warning-ink hover:bg-warning-soft hover:text-warning-ink"
        >
          {migrate.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t('apiKeys.migrating')}
            </>
          ) : (
            <>
              {t('apiKeys.migrateToDatabase')}
              <ArrowRight className="ml-2 h-4 w-4" />
            </>
          )}
        </Button>
      </AlertDescription>
    </Alert>
  )
}

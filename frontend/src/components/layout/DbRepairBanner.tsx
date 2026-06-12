'use client'

import { DatabaseBackup } from 'lucide-react'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useDbRepairStatus } from '@/lib/hooks/use-db-repair-status'

// v0.8.67q — surfaces the launcher's "DB needs repair" flag so the user knows
// to restart, where the backup-first auto-repair (v0.8.67l) runs. Deliberately
// NOT dismissible: source processing is genuinely stuck until they restart, and
// the banner self-clears on the next launch (the repair clears the flag), so
// persisting it is the correct behaviour rather than a nag.
export function DbRepairBanner() {
  const { t } = useTranslation()
  const { data } = useDbRepairStatus()

  if (!data?.needs_repair) return null

  return (
    <div className="px-4 pt-3">
      <Alert className="border-destructive/50 bg-destructive/10 text-destructive">
        <DatabaseBackup className="h-4 w-4" />
        <AlertTitle>
          {t('dbRepair.title', { defaultValue: 'Database needs repair' })}
        </AlertTitle>
        <AlertDescription>
          {t('dbRepair.description', {
            defaultValue:
              'Source processing is paused — the database’s live-query state was corrupted, usually after an unexpected shutdown. Quit Open Notebook Plus (⌘Q) and reopen it: it will be repaired automatically, and a backup is taken first.',
          })}
        </AlertDescription>
      </Alert>
    </div>
  )
}

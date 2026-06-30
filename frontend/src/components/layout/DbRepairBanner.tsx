'use client'

import { DatabaseBackup, RotateCw } from 'lucide-react'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useDbRepairStatus } from '@/lib/hooks/use-db-repair-status'

interface OnpRelaunchWindow {
  ONP?: { relaunch?: () => boolean }
}

// v0.8.67q — surfaces the launcher's "DB needs repair" flag so the user knows
// to restart, where the backup-first auto-repair (v0.8.67l) runs. Deliberately
// NOT dismissible: source processing is genuinely stuck until they restart, and
// the banner self-clears on the next launch (the repair clears the flag), so
// persisting it is the correct behaviour rather than a nag.
//
// v0.8.81 — one-click "Repair & restart": instead of telling the user to ⌘Q +
// reopen manually, relaunch the desktop app via the window.ONP.relaunch bridge
// so the boot-time auto-repair runs. Falls back to a reload in a plain browser
// (dev), where there's no desktop relaunch bridge.
export function DbRepairBanner() {
  const { t } = useTranslation()
  const { data } = useDbRepairStatus()

  if (!data?.needs_repair) return null

  const handleRepairRestart = () => {
    const w = window as unknown as OnpRelaunchWindow & Window
    const relaunched = w.ONP?.relaunch?.()
    if (!relaunched) {
      // No desktop bridge (dev / browser) — a reload is the best fallback.
      window.location.reload()
    }
  }

  return (
    <div className="px-4 pt-3">
      <Alert className="border-destructive/50 bg-destructive/10 text-destructive">
        <DatabaseBackup className="h-4 w-4" />
        <AlertTitle>
          {t('dbRepair.title', { defaultValue: 'Database needs repair' })}
        </AlertTitle>
        <AlertDescription className="space-y-2">
          <p>
            {t('dbRepair.description', {
              defaultValue:
                'Source processing is paused — the database’s live-query state was corrupted, usually after an unexpected shutdown. Restart to repair it automatically (a backup is taken first).',
            })}
          </p>
          <Button size="sm" variant="destructive" onClick={handleRepairRestart}>
            <RotateCw className="mr-2 h-4 w-4" />
            {t('dbRepair.repairRestart', { defaultValue: 'Repair & restart' })}
          </Button>
        </AlertDescription>
      </Alert>
    </div>
  )
}

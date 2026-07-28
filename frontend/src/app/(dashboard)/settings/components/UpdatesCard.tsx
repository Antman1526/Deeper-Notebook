'use client'

// v0.8.70 — Settings card for the in-app update notifier: shows the running
// version, lets the user toggle automatic checking (privacy-gated GitHub
// ping), and offers a manual "Check now". Uses inline defaultValue
// translations to stay clear of the locale-parity contract (same approach as
// the banner).
import { RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  useUpdateCheck,
  useSetUpdateEnabled,
  useCheckForUpdatesNow,
} from '@/lib/hooks/use-updates'

export function UpdatesCard() {
  const { t } = useTranslation()
  const { data } = useUpdateCheck()
  const setEnabled = useSetUpdateEnabled()
  const checkNow = useCheckForUpdatesNow()

  const enabled = data?.enabled ?? true

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('updates.settingsTitle', { defaultValue: 'Updates' })}</CardTitle>
        <CardDescription>
          {t('updates.currentVersion', {
            defaultValue: 'Current version: {{version}}',
            version: data?.current ?? '—',
          })}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="flex items-start gap-3">
          <Checkbox
            checked={enabled}
            onCheckedChange={(checked) => setEnabled.mutate(checked === true)}
            disabled={setEnabled.isPending}
            className="mt-0.5"
          />
          <span className="space-y-1">
            <span className="block text-sm font-medium">
              {t('updates.autoCheckLabel', {
                defaultValue: 'Automatically check for updates',
              })}
            </span>
            <span className="block text-sm text-muted-foreground">
              {t('updates.privacyNote', {
                defaultValue:
                  'When on, Deeper Notebook checks GitHub for new releases on launch (about once a day). This sends a request to GitHub; no other data is shared.',
              })}
            </span>
          </span>
        </label>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => checkNow.mutate()}
            disabled={checkNow.isPending}
          >
            <RefreshCw className={`h-4 w-4${checkNow.isPending ? ' animate-spin' : ''}`} />
            {t('updates.checkNow', { defaultValue: 'Check now' })}
          </Button>
          {data?.update_available ? (
            <span className="text-sm text-primary">
              {t('updates.availableShort', {
                defaultValue: '{{version}} available',
                version: data.latest ?? '',
              })}
            </span>
          ) : data?.last_check ? (
            <span className="text-sm text-muted-foreground">
              {t('updates.upToDate', { defaultValue: "You're up to date." })}
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

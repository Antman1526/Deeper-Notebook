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
  const { data, isError } = useUpdateCheck()
  const setEnabled = useSetUpdateEnabled()
  const checkNow = useCheckForUpdatesNow()

  const enabled = data?.enabled ?? true
  const verification = isError ? 'unknown' : data?.verification ?? 'unknown'

  const releaseNotice = isError ? (
    <span className="text-sm text-muted-foreground">
      Release status unavailable.
    </span>
  ) : !data ? null : data.enabled === false ? (
    <span className="text-sm text-muted-foreground">
      Automatic update checks are off.
    </span>
  ) : verification === 'verified' && data.update_available && data.release_url ? (
    <span className="flex flex-wrap items-center gap-2 text-sm text-primary">
      <span>Verified release available (manual review only)</span>
      <a
        href={data.release_url}
        target="_blank"
        rel="noreferrer"
        className="underline underline-offset-2"
      >
        Open verified release (manual)
      </a>
    </span>
  ) : verification === 'unverified' ? (
    <span className="text-sm text-muted-foreground">
      Release needs verification before it can be offered.
    </span>
  ) : verification === 'unknown' ? (
    <span className="text-sm text-muted-foreground">Release status unavailable.</span>
  ) : data.last_check ? (
    <span className="text-sm text-muted-foreground">
      {t('updates.upToDate', { defaultValue: "You're up to date." })}
    </span>
  ) : null

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
          {releaseNotice}
        </div>
      </CardContent>
    </Card>
  )
}

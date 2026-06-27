'use client'

// v0.8.70 — in-app update notifier banner. Mirrors DbRepairBanner: an Alert in
// the app-shell banner stack, driven by a polling hook, using inline
// defaultValue translations (the established banner pattern — no locale-file
// entries, so it stays clear of the locale-parity contract).
//
// It is a NOTIFIER ONLY: the "Download" button links to the GitHub release
// page; the app never downloads or installs anything itself (it ships unsigned
// today, so silent self-update would be unsafe and OS-blocked anyway).
import { useState } from 'react'
import { Sparkles, X } from 'lucide-react'

import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useUpdateCheck, useSkipVersion } from '@/lib/hooks/use-updates'

export function UpdateBanner() {
  const { t } = useTranslation()
  const { data } = useUpdateCheck()
  const skipVersion = useSkipVersion()
  // Session-only "Later" dismissal — clears on reload, reappears next launch.
  const [dismissed, setDismissed] = useState(false)

  // Only show for a genuine, non-skipped, non-dismissed update with a link.
  if (
    dismissed ||
    !data?.update_available ||
    data.skipped ||
    !data.latest ||
    !data.html_url
  ) {
    return null
  }

  return (
    <div className="px-4 pt-3">
      <Alert className="border-primary/40 bg-primary/5">
        <Sparkles className="h-4 w-4" />
        <AlertTitle>
          {t('updates.title', {
            defaultValue: 'Update available: {{version}}',
            version: data.latest,
          })}
        </AlertTitle>
        <AlertDescription className="flex flex-col gap-3">
          <span>
            {t('updates.description', {
              defaultValue:
                "You're on {{current}}. A newer version is available on GitHub. Downloads are installed manually.",
              current: data.current,
            })}
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <Button asChild size="sm">
              <a href={data.html_url} target="_blank" rel="noreferrer">
                {t('updates.download', { defaultValue: 'Download' })}
              </a>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => skipVersion.mutate(data.latest as string)}
              disabled={skipVersion.isPending}
            >
              {t('updates.skip', { defaultValue: 'Skip this version' })}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setDismissed(true)}
              aria-label={t('updates.later', { defaultValue: 'Later' })}
            >
              <X className="mr-1 h-3.5 w-3.5" />
              {t('updates.later', { defaultValue: 'Later' })}
            </Button>
          </div>
        </AlertDescription>
      </Alert>
    </div>
  )
}

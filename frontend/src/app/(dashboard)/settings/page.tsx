'use client'

import { AppShell } from '@/components/layout/AppShell'
import { SettingsForm } from './components/SettingsForm'
// v0.7.136 — Read-only ObservabilityCard renders the GET /settings/observability
// snapshot below the writable settings form. The two surfaces are
// intentionally separated because the env-derived values aren't
// user-mutable from this UI.
import { ObservabilityCard } from './components/ObservabilityCard'
import { useSettings } from '@/lib/hooks/use-settings'
import { Button } from '@/components/ui/button'
import { RefreshCw } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'

export default function SettingsPage() {
  const { t } = useTranslation()
  const { refetch } = useSettings()

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="p-6">
          <div className="max-w-4xl space-y-6">
            <div className="flex items-center gap-4">
              <h1 className="text-2xl font-bold">{t('navigation.settings')}</h1>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>

            <SettingsForm />
            <ObservabilityCard />
          </div>
        </div>
      </div>
    </AppShell>
  )
}

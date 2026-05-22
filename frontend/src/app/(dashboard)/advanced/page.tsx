'use client'

import { AppShell } from '@/components/layout/AppShell'
import { RebuildEmbeddings } from './components/RebuildEmbeddings'
import { SystemInfo } from './components/SystemInfo'
import { useTranslation } from '@/lib/hooks/use-translation'

export default function AdvancedPage() {
  const { t } = useTranslation()
  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="p-6">
          <div className="max-w-4xl mx-auto space-y-6">
            <div>
              {/* v0.7.180 — text-3xl font-bold → text-3xl font-semibold
                  tracking-tight, matching the v0.7.153/v0.7.164 H1 standard
                  (Settings, Podcasts, Models, Studio, Notebooks, Search,
                  Transformations all use this now). Advanced was the last
                  dashboard page on the legacy `font-bold` H1. */}
              <h1 className="text-3xl font-semibold tracking-tight">{t('advanced.title')}</h1>
              <p className="text-muted-foreground mt-2">
                {t('advanced.desc')}
              </p>
            </div>

            <SystemInfo />
            <RebuildEmbeddings />
          </div>
        </div>
      </div>
    </AppShell>
  )
}

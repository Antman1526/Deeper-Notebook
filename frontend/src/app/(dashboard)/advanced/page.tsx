'use client'

import { AppShell } from '@/components/layout/AppShell'
import { RebuildEmbeddings } from './components/RebuildEmbeddings'
import { SystemInfo } from './components/SystemInfo'
import { useTranslation } from '@/lib/hooks/use-translation'
import { SystemRouteFrame } from '@/components/deeper-notebook/route-frames/SystemRouteFrames'

export default function AdvancedPage() {
  const { t } = useTranslation()
  return (
    <AppShell>
      <SystemRouteFrame route="/advanced" description={t('advanced.desc')}>
        {/* v0.7.183 — outer padding promoted from bare `p-6` to the
            v0.7.180 dashboard-page standard `px-6 py-10 sm:px-8`
            (matches Settings, Podcasts, Search, Models). Adds the
            vertical breathing room every other dashboard has, plus
            the wider sm-breakpoint horizontal padding so content
            isn't hugging the rail on mid-width laptops. */}
        <div className="mx-auto max-w-4xl space-y-6 rounded-lg bg-[var(--dn-folio-paper)] p-4 sm:p-6">
            <div>
              {/* v0.7.180 — text-3xl font-bold → text-3xl font-semibold
                  tracking-tight, matching the v0.7.153/v0.7.164 H1 standard
                  (Settings, Podcasts, Models, Studio, Notebooks, Search,
                  Transformations all use this now). Advanced was the last
                  dashboard page on the legacy `font-bold` H1. */}
              <h2 className="text-2xl font-semibold">{t('advanced.title')}</h2>
            </div>

            <SystemInfo />
            <RebuildEmbeddings />
        </div>
      </SystemRouteFrame>
    </AppShell>
  )
}

'use client'

import Link from 'next/link'

import { SourceCover } from './SourceCover'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { SourceListResponse } from '@/lib/types/api'

type RecentSourceStripProps = {
  sources: SourceListResponse[]
}

export function RecentSourceStrip({ sources }: RecentSourceStripProps) {
  const { t } = useTranslation()
  if (sources.length === 0) return null

  return (
    <section aria-label={t('workspace.recentSourceStrip.ariaLabel')} className="min-w-0 space-y-3">
      <div>
        <h2 className="text-base font-semibold">{t('workspace.recentSourceStrip.heading')}</h2>
        <p className="text-sm text-muted-foreground">{t('workspace.recentSourceStrip.description')}</p>
      </div>
      {/* v0.8.130 — Phase 4b: li items; explicit roles keep list semantics in Safari. */}
      <ul className="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,10rem),1fr))] gap-3" role="list">
        {sources.map(source => {
          const title = source.title?.trim() || t('sources.untitledSource')
          return (
            <li className="min-w-0" key={source.id} role="listitem">
              <Link
                aria-label={t('workspace.recentSourceStrip.openLabel', { title })}
                className="block min-h-11 min-w-11 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                href={`/sources/${encodeURIComponent(source.id)}`}
              >
                <SourceCover source={source} variant="compact" />
              </Link>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

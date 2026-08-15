import Link from 'next/link'

import { SourceCover } from './SourceCover'
import type { SourceListResponse } from '@/lib/types/api'

type RecentSourceStripProps = {
  sources: SourceListResponse[]
}

export function RecentSourceStrip({ sources }: RecentSourceStripProps) {
  if (sources.length === 0) return null

  return (
    <section aria-label="Recent visual sources" className="min-w-0 space-y-3">
      <div>
        <h2 className="text-base font-semibold">Recent sources</h2>
        <p className="text-sm text-muted-foreground">Recently updated source material with local visual context.</p>
      </div>
      <div className="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,10rem),1fr))] gap-3" role="list">
        {sources.map(source => {
          const title = source.title?.trim() || 'Untitled source'
          return (
            <article className="min-w-0" key={source.id} role="listitem">
              <Link
                aria-label={`Open ${title}`}
                className="block min-h-11 min-w-11 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                href={`/sources/${encodeURIComponent(source.id)}`}
              >
                <SourceCover source={source} variant="compact" />
              </Link>
            </article>
          )
        })}
      </div>
    </section>
  )
}

import type { ReactNode } from 'react'

import { SourceCover } from './SourceCover'
import type { SourceListResponse } from '@/lib/types/api'

type SourceGalleryProps = {
  sources: SourceListResponse[]
  selectedId?: string | null
  filters?: ReactNode
  onSelect?: (sourceId: string) => void
  onOpen?: (sourceId: string) => void
  onRefresh?: (sourceId: string) => void
  onRemove?: (sourceId: string) => void
  onDelete?: (sourceId: string) => void
}

export function SourceGallery({
  sources,
  selectedId,
  filters,
  onSelect,
  onOpen,
  onRefresh,
  onRemove,
  onDelete,
}: SourceGalleryProps) {
  const featuredId = selectedId && sources.some(source => source.id === selectedId) ? selectedId : sources[0]?.id

  return (
    <section className="dn-source-gallery" data-dn-source-gallery="true" aria-label="Source gallery">
      {filters ? <div className="dn-source-gallery__filters">{filters}</div> : null}
      <div className="dn-source-gallery__grid" role="list">
        {sources.map(source => {
          const title = source.title?.trim() || 'Untitled source'
          const featured = source.id === featuredId
          return (
            <article
              className="dn-source-gallery__card"
              data-featured={featured}
              data-testid={`source-gallery-card-${source.id}`}
              key={source.id}
              role="listitem"
            >
              <button
                type="button"
                className="dn-source-gallery__select"
                onClick={() => onSelect?.(source.id)}
                aria-pressed={featured}
              >
                Select {title}
              </button>
              <SourceCover
                source={source}
                priority={featured}
                onOpen={onOpen}
                onRefresh={onRefresh}
                onRemove={onRemove}
                onDelete={onDelete}
              />
            </article>
          )
        })}
      </div>
    </section>
  )
}

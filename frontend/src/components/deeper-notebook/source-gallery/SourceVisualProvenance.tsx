'use client'

import { useTranslation } from '@/lib/hooks/use-translation'
import type { SourceVisualReceipt } from '@/lib/types/source-visuals'

const ORIGIN_LABEL_KEYS = {
  embedded: 'artifacts.sourceVisualProvenance.origin.embedded',
  video_frame: 'artifacts.sourceVisualProvenance.origin.videoFrame',
  audio_artwork: 'artifacts.sourceVisualProvenance.origin.audioArtwork',
} as const

export function sourceVisualOriginLabel(
  origin: SourceVisualReceipt['origin'],
  t: (key: string) => string,
): string {
  return t(ORIGIN_LABEL_KEYS[origin])
}

export function SourceVisualProvenance({ origin }: { origin: SourceVisualReceipt['origin'] }) {
  const { t } = useTranslation()
  return (
    <p className="dn-source-gallery__provenance" aria-label={t('artifacts.sourceVisualProvenance.imageOrigin')}>
      {sourceVisualOriginLabel(origin, t)}
    </p>
  )
}

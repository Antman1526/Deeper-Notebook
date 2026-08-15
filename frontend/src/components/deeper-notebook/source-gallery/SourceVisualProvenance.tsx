import type { SourceVisualReceipt } from '@/lib/types/source-visuals'

const ORIGIN_LABELS = {
  embedded: 'Embedded image',
  video_frame: 'Video frame',
  audio_artwork: 'Embedded artwork',
} as const

export function sourceVisualOriginLabel(origin: SourceVisualReceipt['origin']): string {
  return ORIGIN_LABELS[origin]
}

export function SourceVisualProvenance({ origin }: { origin: SourceVisualReceipt['origin'] }) {
  return (
    <p className="dn-source-gallery__provenance" aria-label="Image origin">
      {sourceVisualOriginLabel(origin)}
    </p>
  )
}

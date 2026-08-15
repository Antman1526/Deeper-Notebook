'use client'

import { useMemo, useRef, useState } from 'react'

import { SourceVisualProvenance, sourceVisualOriginLabel } from './SourceVisualProvenance'
import type { SourceListResponse } from '@/lib/types/api'
import type { SourceVisualReceipt } from '@/lib/types/source-visuals'

type SourceCoverProps = {
  source: SourceListResponse
  variant?: 'card' | 'compact'
  priority?: boolean
  onOpen?: (sourceId: string) => void
  onRefresh?: (sourceId: string) => void | Promise<void>
  onRemove?: (sourceId: string) => void | Promise<void>
}

function sourceTypeLabel(sourceType: SourceListResponse['source_type']): string {
  if (!sourceType) return 'Source'
  return sourceType.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

function statusCopy(source: SourceListResponse): string {
  switch (source.visual_status?.state) {
    case 'queued':
      return 'Visual cover queued'
    case 'processing':
      return 'Preparing visual cover'
    case 'failed':
    case 'unavailable':
      return 'Visual cover unavailable'
    default:
      return 'Visual cover unavailable'
  }
}

function hasExactLocator(value: unknown, key: string, predicate: (candidate: unknown) => boolean): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const locator = value as Record<string, unknown>
  return Object.keys(locator).length === 1 && key in locator && predicate(locator[key])
}

function isResourceId(candidate: unknown): candidate is string {
  return typeof candidate === 'string' && candidate.trim().length > 0 && candidate.length <= 128
}

function isPage(candidate: unknown): candidate is number {
  return typeof candidate === 'number' && Number.isInteger(candidate) && candidate >= 1 && candidate <= 24
}

function isNonnegativeInteger(candidate: unknown): candidate is number {
  return typeof candidate === 'number' && Number.isInteger(candidate) && candidate >= 0
}

function hasValidLocator(value: SourceVisualReceipt): boolean {
  switch (value.origin) {
    case 'embedded':
      return hasExactLocator(value.source_locator, 'page', isPage)
        || hasExactLocator(value.source_locator, 'resource_id', isResourceId)
    case 'video_frame':
      return hasExactLocator(value.source_locator, 'timestamp_ms', isNonnegativeInteger)
    case 'audio_artwork':
      return hasExactLocator(value.source_locator, 'resource_id', isResourceId)
    default:
      return false
  }
}

function isReceiptForSource(value: SourceVisualReceipt | null | undefined, sourceId: string): value is SourceVisualReceipt {
  if (!value || value.source_id !== sourceId || value.mime_type !== 'image/webp') return false
  if (!Number.isInteger(value.width) || !Number.isInteger(value.height) || value.width < 1 || value.height < 1) return false
  if (!/^[0-9a-f]{64}$/.test(value.content_sha256) || !/^[0-9a-f]{64}$/.test(value.asset_sha256) || !value.alt_text.trim()) return false
  const expectedPrefix = `/api/sources/${encodeURIComponent(sourceId)}/visual?v=`
  const opaqueVersion = value.asset_url.startsWith(expectedPrefix)
    ? value.asset_url.slice(expectedPrefix.length)
    : ''
  return /^[0-9a-f]{64}$/.test(opaqueVersion) && hasValidLocator(value)
}

export function SourceCover({
  source,
  variant = 'card',
  priority = false,
  onOpen,
  onRefresh,
  onRemove,
}: SourceCoverProps) {
  const [failedAssetIdentity, setFailedAssetIdentity] = useState<string | null>(null)
  const [pendingIdentity, setPendingIdentity] = useState<string | null>(null)
  const pendingIdentityRef = useRef<string | null>(null)
  const title = source.title?.trim() || 'Untitled source'
  const validVisual = isReceiptForSource(source.visual, source.id) ? source.visual : null
  const assetIdentity = validVisual ? `${source.id}|${validVisual.asset_sha256}` : null
  const visual = validVisual && failedAssetIdentity !== assetIdentity ? validVisual : null
  const identity = useMemo(
    () => [source.id, source.updated, source.visual?.content_sha256 ?? '', source.visual_status?.updated_at ?? ''].join('|'),
    [source.id, source.updated, source.visual?.content_sha256, source.visual_status?.updated_at],
  )
  const pending = pendingIdentity === identity

  function dispatch(action: ((sourceId: string) => void | Promise<void>) | undefined) {
    if (!action || pending || pendingIdentityRef.current === identity) return
    const dispatchedIdentity = identity
    pendingIdentityRef.current = dispatchedIdentity
    setPendingIdentity(dispatchedIdentity)

    try {
      const result = action(source.id)
      if (result) {
        void result.catch(() => {
          if (pendingIdentityRef.current === dispatchedIdentity) {
            pendingIdentityRef.current = null
          }
          setPendingIdentity(current => current === dispatchedIdentity ? null : current)
        })
      }
    } catch {
      if (pendingIdentityRef.current === dispatchedIdentity) {
        pendingIdentityRef.current = null
      }
      setPendingIdentity(current => current === dispatchedIdentity ? null : current)
    }
  }

  return (
    <section className={`dn-source-cover dn-source-cover--${variant}`} data-dn-source-cover="true">
      <div className="dn-source-cover__visual" data-dn-source-cover-aspect>
        {visual ? (
          <>
            {/* The receipt is an opaque same-origin, bounded WebP derivative, not an external image URL. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={visual.asset_url}
              alt={`${title} — ${sourceVisualOriginLabel(visual.origin)}: ${visual.alt_text}`}
              width={visual.width}
              height={visual.height}
              loading={priority ? 'eager' : 'lazy'}
              decoding="async"
              onError={() => setFailedAssetIdentity(assetIdentity)}
            />
            <SourceVisualProvenance origin={visual.origin} />
          </>
        ) : (
          <div className="dn-source-cover__fallback">
            <span className="dn-source-cover__shape" aria-hidden="true" />
            <p className="dn-source-cover__title">{title}</p>
            <p className="dn-source-cover__type">{sourceTypeLabel(source.source_type)}</p>
            <p className="dn-source-cover__status" role="status">{statusCopy(source)}</p>
          </div>
        )}
      </div>

      {(onOpen || onRefresh || onRemove) ? (
        <div className="dn-source-cover__actions">
          {onOpen ? (
            <button type="button" onClick={() => onOpen(source.id)}>
              Open {title}
            </button>
          ) : null}
          {onRefresh ? (
            <button type="button" disabled={pending} onClick={() => dispatch(onRefresh)}>
              Refresh visual for {title}
            </button>
          ) : null}
          {onRemove ? (
            <button type="button" disabled={pending} onClick={() => dispatch(onRemove)}>
              Remove visual for {title}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

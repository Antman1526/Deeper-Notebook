import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SourceCover } from './SourceCover'
import type { SourceListResponse } from '@/lib/types/api'
import type { SourceVisualReceipt, SourceVisualStatus } from '@/lib/types/source-visuals'

const hash = 'a'.repeat(64)
const timestamp = '2026-08-15T12:00:00Z'

function visual(overrides: Partial<SourceVisualReceipt> = {}): SourceVisualReceipt {
  return {
    source_id: 'source:one',
    content_sha256: hash,
    asset_sha256: hash,
    alt_text: 'Neutral source-derived cover',
    width: 640,
    height: 360,
    mime_type: 'image/webp',
    asset_url: `/api/sources/source%3Aone/visual?v=${hash}`,
    created_at: timestamp,
    updated_at: timestamp,
    origin: 'embedded',
    source_locator: { page: 1 },
    ...overrides,
  } as SourceVisualReceipt
}

function source(overrides: Partial<SourceListResponse> = {}): SourceListResponse {
  return {
    id: 'source:one',
    title: 'Field notes',
    asset: null,
    embedded: true,
    embedded_chunks: 1,
    insights_count: 0,
    created: timestamp,
    updated: timestamp,
    source_type: 'upload',
    visual: visual(),
    visual_status: null,
    ...overrides,
  }
}

describe('SourceCover', () => {
  it.each([
    ['embedded', { page: 1 }, 'Embedded image'],
    ['video_frame', { timestamp_ms: 4000 }, 'Video frame'],
    ['audio_artwork', { resource_id: 'cover' }, 'Embedded artwork'],
  ] as const)('renders %s provenance and a useful image name', (origin, source_locator, originLabel) => {
    render(<SourceCover source={source({ visual: visual({ origin, source_locator } as Partial<SourceVisualReceipt>) })} priority />)

    const image = screen.getByRole('img', { name: `Field notes — ${originLabel}: Neutral source-derived cover` })
    expect(image).toHaveAttribute('src', `/api/sources/source%3Aone/visual?v=${hash}`)
    expect(image).toHaveAttribute('width', '640')
    expect(image).toHaveAttribute('height', '360')
    expect(image).toHaveAttribute('loading', 'eager')
    expect(image).toHaveAttribute('decoding', 'async')
    expect(screen.getByText(originLabel)).toBeVisible()
  })

  it('uses a lazy fixed-ratio image box outside the priority region', () => {
    const { container } = render(<SourceCover source={source()} priority={false} />)

    expect(screen.getByRole('img')).toHaveAttribute('loading', 'lazy')
    expect(container.querySelector('[data-dn-source-cover-aspect]')).toBeInTheDocument()
  })

  it('uses intentional typographic fallbacks for missing, invalid, and broken visuals', () => {
    const { container, rerender } = render(<SourceCover source={source({ visual: null })} />)

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('Field notes')).toBeVisible()
    expect(screen.getByText('Upload')).toBeVisible()
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument()

    rerender(<SourceCover source={source({ visual: { asset_url: 'https://untrusted.invalid/image.webp' } as never })} />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()

    rerender(<SourceCover source={source({ visual: visual({ asset_url: `/api/sources/source%3Aone/visual?v=${'b'.repeat(64)}` }) })} />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()

    rerender(<SourceCover source={source()} />)
    fireEvent.error(screen.getByRole('img'))
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('Field notes')).toBeVisible()
  })

  it('keeps a broken asset suppressed but accepts a newly generated visual receipt', () => {
    const { rerender } = render(<SourceCover source={source()} />)

    fireEvent.error(screen.getByRole('img'))
    expect(screen.queryByRole('img')).not.toBeInTheDocument()

    rerender(<SourceCover source={source()} />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()

    const nextHash = 'b'.repeat(64)
    rerender(
      <SourceCover
        source={source({
          visual: visual({
            asset_sha256: nextHash,
            asset_url: `/api/sources/source%3Aone/visual?v=${nextHash}`,
          }),
        })}
      />,
    )
    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      `/api/sources/source%3Aone/visual?v=${nextHash}`,
    )
  })

  it.each([
    ['queued', 'Visual cover queued'],
    ['processing', 'Preparing visual cover'],
    ['failed', 'Visual cover unavailable'],
    ['unavailable', 'Visual cover unavailable'],
  ] as const)('uses safe %s status copy after reload without exposing raw error codes', (state, copy) => {
    const visual_status: SourceVisualStatus = {
      state,
      command_id: 'command:one',
      error_code: 'internal.cache_path_leaked',
      updated_at: timestamp,
    }
    render(<SourceCover source={source({ visual: null, visual_status })} />)

    expect(screen.getByText(copy)).toBeVisible()
    expect(screen.queryByText('internal.cache_path_leaked')).not.toBeInTheDocument()
  })

  it('dispatches each visual action once and keeps same-identity refresh disabled', () => {
    const onRefresh = vi.fn()
    const onRemove = vi.fn()
    const { rerender } = render(<SourceCover source={source({ visual: null })} onRefresh={onRefresh} onRemove={onRemove} />)

    const refresh = screen.getByRole('button', { name: 'Refresh visual for Field notes' })
    fireEvent.click(refresh)
    fireEvent.click(refresh)
    expect(onRefresh).toHaveBeenCalledOnce()
    expect(onRefresh).toHaveBeenCalledWith('source:one')
    expect(refresh).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Remove visual for Field notes' })).toBeDisabled()

    rerender(<SourceCover source={source({ visual: null })} onRefresh={onRefresh} onRemove={onRemove} />)
    expect(screen.getByRole('button', { name: 'Refresh visual for Field notes' })).toBeDisabled()

    rerender(<SourceCover source={source({ id: 'source:two', title: 'Second source', visual: null })} onRefresh={onRefresh} onRemove={onRemove} />)
    fireEvent.click(screen.getByRole('button', { name: 'Remove visual for Second source' }))
    expect(onRemove).toHaveBeenCalledOnce()
    expect(onRemove).toHaveBeenCalledWith('source:two')
  })
})

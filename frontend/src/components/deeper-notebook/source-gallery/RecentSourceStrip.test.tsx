import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { sourcesApi } from '@/lib/api/sources'
import type { SourceListResponse } from '@/lib/types/api'
import { RecentSourceStrip } from './RecentSourceStrip'

// Keys come back unchanged; interpolated values are appended so names that
// embed a source title stay distinguishable.
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key} ${Object.values(opts).join(' ')}` : key,
  }),
}))

const hash = 'a'.repeat(64)
const opaqueToken = 'b'.repeat(64)

const source: SourceListResponse = {
  id: 'source:one',
  title: 'Field notes',
  source_type: 'upload',
  asset: null,
  embedded: true,
  embedded_chunks: 1,
  insights_count: 0,
  created: '2026-08-10T00:00:00Z',
  updated: '2026-08-10T00:01:00Z',
  visual: {
    source_id: 'source:one',
    content_sha256: hash,
    asset_sha256: hash,
    alt_text: 'Handwritten field observations',
    width: 640,
    height: 360,
    mime_type: 'image/webp',
    asset_url: `/api/sources/source%3Aone/visual?v=${opaqueToken}`,
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:01:00Z',
    origin: 'embedded',
    source_locator: { page: 1 },
  },
}

describe('RecentSourceStrip', () => {
  it('renders typed actionless compact covers without owning a source fetch', () => {
    const list = vi.spyOn(sourcesApi, 'list')

    render(<RecentSourceStrip sources={[source]} />)

    expect(screen.getByRole('region', { name: 'workspace.recentSourceStrip.ariaLabel' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'workspace.recentSourceStrip.openLabel Field notes' })).toHaveAttribute('href', '/sources/source%3Aone')
    expect(screen.getByRole('img', { name: /Handwritten field observations/ })).toBeVisible()
    expect(screen.queryByRole('button', { name: /workspace\.sourceCoverActions\.refreshVisual/ })).not.toBeInTheDocument()
    expect(list).not.toHaveBeenCalled()

    list.mockRestore()
  })

  it('renders nothing when the route supplies no recent visual sources', () => {
    const { container } = render(<RecentSourceStrip sources={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})

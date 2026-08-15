import { fireEvent, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'

import { SourceGallery } from './SourceGallery'
import type { SourceListResponse } from '@/lib/types/api'

const timestamp = '2026-08-15T12:00:00Z'
const css = readFileSync('src/components/deeper-notebook/source-gallery/source-gallery.css', 'utf8')

function source(id: string, title: string): SourceListResponse {
  return {
    id,
    title,
    asset: null,
    embedded: true,
    embedded_chunks: 1,
    insights_count: 0,
    created: timestamp,
    updated: timestamp,
    source_type: 'upload',
    visual: null,
    visual_status: { state: 'unavailable', command_id: null, error_code: null, updated_at: timestamp },
  }
}

describe('SourceGallery', () => {
  it('selects the feature card, exposes filters, and only dispatches caller callbacks', () => {
    const onSelect = vi.fn()
    const onOpen = vi.fn()
    const sources = [source('source:one', 'First source'), source('source:two', 'Second source')]

    render(
      <SourceGallery
        sources={sources}
        selectedId="source:two"
        filters={<button type="button">Ready sources</button>}
        onSelect={onSelect}
        onOpen={onOpen}
      />,
    )

    expect(screen.getByRole('button', { name: 'Ready sources' })).toBeVisible()
    expect(screen.getByTestId('source-gallery-card-source:two')).toHaveAttribute('data-featured', 'true')
    expect(screen.getByTestId('source-gallery-card-source:one')).toHaveAttribute('data-featured', 'false')

    fireEvent.click(screen.getByRole('button', { name: 'Select First source' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open First source' }))
    expect(onSelect).toHaveBeenCalledWith('source:one')
    expect(onOpen).toHaveBeenCalledWith('source:one')
  })

  it('provides the bounded container, compact reflow, target, contrast, and no-motion CSS contract', () => {
    expect(css).toContain('container: source-gallery / inline-size')
    expect(css).toContain('repeat(auto-fit, minmax(min(100%, 14rem), 1fr))')
    expect(css).toContain('@container source-gallery (max-width: 34rem)')
    expect(css).toMatch(
      /@container source-gallery \(max-width: 34rem\)[\s\S]*?\.dn-source-cover \{[\s\S]*?grid-column: 1 \/ -1/,
    )
    expect(css).toContain('min-height: 44px')
    expect(css).toContain('min-width: 0')
    expect(css).toContain('@media (forced-colors: active)')
    expect(css).toContain('@media (prefers-reduced-motion: reduce)')
    expect(css).not.toContain('@keyframes')
    expect(css).not.toContain('scroll-snap')
  })
})

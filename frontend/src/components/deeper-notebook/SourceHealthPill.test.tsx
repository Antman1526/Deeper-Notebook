import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { getSourceReadiness, SourceHealthPill } from './SourceHealthPill'
import type { SourceListResponse } from '@/lib/types/api'

function source(overrides: Partial<SourceListResponse>): SourceListResponse {
  return {
    id: 'source:one',
    title: 'Source One',
    asset: null,
    embedded: true,
    embedded_chunks: 3,
    insights_count: 0,
    created: '2026-06-23T00:00:00Z',
    updated: '2026-06-23T00:00:00Z',
    ...overrides,
  }
}

describe('SourceHealthPill', () => {
  it.each([
    [source({ status: 'completed', embedded: true }), 'workspace.sourceHealthPill.ready', false],
    [source({ status: 'failed', embedded: false }), 'workspace.sourceHealthPill.failed', true],
    [source({ status: 'running', embedded: false }), 'workspace.sourceHealthPill.processing', true],
    [source({ status: 'queued', embedded: false }), 'workspace.sourceHealthPill.queued', true],
    [source({ status: 'completed', embedded: false }), 'workspace.sourceHealthPill.notEmbedded', true],
    [source({ status: 'completed', embedded: true, extraction_quality: 'no_text' }), 'workspace.sourceHealthPill.noText', true],
    [source({ status: 'completed', embedded: true, extraction_quality: 'low_text' }), 'workspace.sourceHealthPill.lowText', false],
  ])('renders %s source readiness', (row, label, blocksGeneration) => {
    render(<SourceHealthPill source={row} />)

    expect(screen.getByText(label)).toBeInTheDocument()
    expect(getSourceReadiness(row).blocksGeneration).toBe(blocksGeneration)
  })
})

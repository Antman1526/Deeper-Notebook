import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { SourceListResponse } from '@/lib/types/api'
import KnowledgePage from './page'

const { mockVisualSystemEnabled, mockSourceVisualsEnabled, mockRecentSources } = vi.hoisted(() => ({
  mockVisualSystemEnabled: vi.fn(() => false),
  mockSourceVisualsEnabled: vi.fn(() => false),
  mockRecentSources: vi.fn(),
}))

vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/vault/KnowledgeExplorer', () => ({ KnowledgeExplorer: () => <section aria-label="Knowledge explorer">Vault authority</section> }))
vi.mock('@/lib/features', () => ({
  isVisualSystemV2Enabled: mockVisualSystemEnabled,
  isSourceVisualsEnabled: mockSourceVisualsEnabled,
}))
vi.mock('@/lib/hooks/use-source-visuals', () => ({ useRecentVisualSources: mockRecentSources }))

const recentSource: SourceListResponse = {
  id: 'source:one', title: 'Field notes', source_type: 'upload', asset: null,
  embedded: true, embedded_chunks: 1, insights_count: 0,
  created: '2026-08-10T00:00:00Z', updated: '2026-08-10T00:01:00Z', visual: null,
}

describe('KnowledgePage source visuals', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockVisualSystemEnabled.mockReturnValue(false)
    mockSourceVisualsEnabled.mockReturnValue(false)
    mockRecentSources.mockReturnValue({ data: [recentSource] })
  })

  it('keeps KnowledgeExplorer authoritative and renders one bounded recent strip when both gates are on', () => {
    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)

    render(<KnowledgePage />)

    expect(screen.getByRole('region', { name: 'Knowledge explorer' })).toHaveTextContent('Vault authority')
    expect(mockRecentSources).toHaveBeenCalledOnce()
    expect(mockRecentSources).toHaveBeenCalledWith(4)
    expect(screen.getByRole('region', { name: 'Recent visual sources' })).toBeInTheDocument()
  })

  it.each([
    ['visual system off', false, true],
    ['source visuals off', true, false],
  ])('keeps the exact Knowledge page without a recent strip when %s', (_label, visualSystem, sourceVisuals) => {
    mockVisualSystemEnabled.mockReturnValue(visualSystem)
    mockSourceVisualsEnabled.mockReturnValue(sourceVisuals)

    render(<KnowledgePage />)

    expect(screen.getByRole('region', { name: 'Knowledge explorer' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Recent visual sources' })).not.toBeInTheDocument()
  })
})

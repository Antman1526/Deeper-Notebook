import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const routePlan = vi.hoisted(() => ({ data: undefined as any, isError: false, isLoading: false }))
vi.mock('@/lib/hooks/use-local-models', () => ({ useModelRoutePlan: () => routePlan }))

import { KnowledgePodcastPane } from './KnowledgePodcastPane'

describe('KnowledgePodcastPane', () => {
  it('shows the current selection without generating a podcast on mount', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')

    render(<KnowledgePodcastPane seedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(screen.getByText('1 selected document')).toBeInTheDocument()
    expect(screen.getByText('Podcast generation opens in Phase 2.')).toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalledWith('/podcasts/generate', expect.anything())

    fetchSpy.mockRestore()
  })

  it('shows redacted plans for every Podcast stage', () => {
    routePlan.data = { role: 'podcast_outline', outcome: 'ready', selected_model_id: 'qwen-local', selected_provider: 'mlx', resource_tier: 'standard', selection_source: 'automatic', route_reason: 'Verified local route.', escalation_model_ids: [], blocked_reason: null, selected_fingerprint: 'fingerprint', selected_measurements: {} }
    render(<KnowledgePodcastPane seedDocumentIds={[]} />)
    for (const title of ['Evidence route', 'Storyboard route', 'Script route', 'Verification route', 'Voice route']) expect(screen.getByText(title)).toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const routePlan = vi.hoisted(() => ({ data: undefined as any, isError: false, isLoading: false }))
const savedSettings = vi.hoisted(() => ({ data: { execution_policy: 'strict_local', compute_profile: 'balanced', role_overrides: {} } as any }))
const routePlanCalls = vi.hoisted(() => [] as unknown[][])
vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelSettings: () => savedSettings,
  useModelRoutePlan: (...args: unknown[]) => { routePlanCalls.push(args); return routePlan },
}))

import { KnowledgePodcastPane } from './KnowledgePodcastPane'

describe('KnowledgePodcastPane', () => {
  it('plans every Podcast stage with saved Local Preferred settings and overrides', () => {
    savedSettings.data = { execution_policy: 'local_preferred', compute_profile: 'maximum_quality', role_overrides: { podcast_script: 'script-override', text_to_speech: 'voice-override' } }
    routePlanCalls.length = 0
    render(<KnowledgePodcastPane seedDocumentIds={[]} />)
    expect(routePlanCalls).toContainEqual([{ role: 'podcast_script', execution_policy: 'local_preferred', compute_profile: 'maximum_quality', role_override_model_id: 'script-override', modalities: ['text'] }])
    expect(routePlanCalls).toContainEqual([{ role: 'text_to_speech', execution_policy: 'local_preferred', compute_profile: 'maximum_quality', role_override_model_id: 'voice-override', modalities: ['audio'] }])
  })

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

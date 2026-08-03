import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { LocalModelSettings, ModelRoutePlan } from '@/lib/api/local-models'

const routePlan = vi.hoisted(() => ({ data: undefined as ModelRoutePlan | undefined, isError: false, isLoading: false }))
const savedSettings = vi.hoisted(() => ({ data: {
  model_dir: '',
  execution_policy: 'strict_local',
  compute_profile: 'balanced',
  local_model_memory_limit_bytes: null,
  role_overrides: {},
  trusted_external_model_roots: [],
} as LocalModelSettings }))
const routePlanCalls = vi.hoisted(() => [] as unknown[][])

const localSettings = (overrides: Partial<LocalModelSettings> = {}): LocalModelSettings => ({
  model_dir: '',
  execution_policy: 'strict_local',
  compute_profile: 'balanced',
  local_model_memory_limit_bytes: null,
  role_overrides: {},
  trusted_external_model_roots: [],
  ...overrides,
})
vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelSettings: () => savedSettings,
  useModelRoutePlan: (...args: unknown[]) => { routePlanCalls.push(args); return routePlan },
}))

import { KnowledgePodcastPane } from './KnowledgePodcastPane'

describe('KnowledgePodcastPane', () => {
  it('plans every Podcast stage with saved Local Preferred settings and overrides', () => {
    savedSettings.data = localSettings({
      execution_policy: 'local_preferred',
      compute_profile: 'maximum_quality',
      role_overrides: { podcast_script: 'script-override', text_to_speech: 'voice-override' },
    })
    routePlanCalls.length = 0
    render(<KnowledgePodcastPane seedDocumentIds={[]} />)
    expect(routePlanCalls).toContainEqual([{ role: 'podcast_script', execution_policy: 'local_preferred', compute_profile: 'maximum_quality', role_override_model_id: 'script-override', modalities: ['text'] }])
    expect(routePlanCalls).toContainEqual([{ role: 'text_to_speech', execution_policy: 'local_preferred', compute_profile: 'maximum_quality', role_override_model_id: 'voice-override', modalities: ['audio'] }])
  })

  it('shows the current selection without generating a podcast on mount', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')

    render(<KnowledgePodcastPane seedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(screen.getByText(/1 selected reference/u)).toBeInTheDocument()
    expect(screen.getByText(/Production remains a separate confirmation/u)).toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalledWith('/podcasts/generate', expect.anything())

    fetchSpy.mockRestore()
  })

  it('shows redacted plans for every Podcast stage', () => {
    routePlan.data = { role: 'podcast_outline', outcome: 'ready', selected_model_id: 'qwen-local', selected_provider: 'mlx', resource_tier: 'standard', selection_source: 'automatic', route_reason: 'Verified local route.', escalation_model_ids: [], blocked_reason: null, selected_fingerprint: 'fingerprint', selected_measurements: {} }
    render(<KnowledgePodcastPane seedDocumentIds={[]} />)
    for (const title of ['Evidence route', 'Storyboard route', 'Script route', 'Verification route', 'Voice route']) expect(screen.getByText(title)).toBeInTheDocument()
  })

  it('uses the shared Studio with an honest locked Phase 3 boundary', () => {
    render(<KnowledgePodcastPane seedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(screen.getByRole('region', { name: 'Podcast Intelligence Studio' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Research Set' })).toBeInTheDocument()
    expect(screen.getByText('Evidence')).toBeInTheDocument()
    expect(screen.getAllByText('Available after intellectual engine upgrade')).toHaveLength(2)
  })
})

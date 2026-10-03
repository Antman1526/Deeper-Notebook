import { render, screen, waitFor } from '@testing-library/react'
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

  it('shows a stable lazy loading shell and then the current selection without generating a podcast on mount', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')

    render(<KnowledgePodcastPane seedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(screen.getByText('podcasts.knowledgePodcastPane.loadingStudio')).toBeInTheDocument()
    // The first test to resolve the lazy PodcastStudio chunk pays the cold module-graph transform, which can exceed waitFor's 1s default under parallel load.
    await waitFor(() => expect(screen.getByText('podcasts.researchSetPanel.selectedReferencesOne')).toBeInTheDocument(), { timeout: 10_000 })
    expect(screen.getByText('podcasts.podcastStudio.description')).toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalledWith('/podcasts/generate', expect.anything())

    fetchSpy.mockRestore()
  })

  it('shows redacted plans for every Podcast stage', async () => {
    routePlan.data = { role: 'podcast_outline', outcome: 'ready', selected_model_id: 'qwen-local', selected_provider: 'mlx', resource_tier: 'standard', selection_source: 'automatic', route_reason: 'Verified local route.', escalation_model_ids: [], blocked_reason: null, selected_fingerprint: 'fingerprint', selected_measurements: {} }
    render(<KnowledgePodcastPane seedDocumentIds={[]} />)
    await waitFor(() => {
      for (const title of ['podcasts.knowledgePodcastPane.evidenceRoute', 'podcasts.knowledgePodcastPane.storyboardRoute', 'podcasts.knowledgePodcastPane.scriptRoute', 'podcasts.knowledgePodcastPane.verificationRoute', 'podcasts.knowledgePodcastPane.voiceRoute']) expect(screen.getByText(title)).toBeInTheDocument()
    }, { timeout: 10_000 })
  })

  it('preserves planner provider, tier, source, and safe override choices in the Knowledge pane', async () => {
    routePlan.data = {
      role: 'podcast_outline', outcome: 'ready', selected_model_id: 'qwen-local', selected_provider: 'mlx',
      resource_tier: 'standard', selection_source: 'automatic', route_reason: 'Verified local route.',
      escalation_model_ids: ['qwen-heavy'], blocked_reason: null, selected_fingerprint: 'fingerprint', selected_measurements: {},
    }
    render(<KnowledgePodcastPane seedDocumentIds={[]} />)

    await waitFor(() => expect(screen.getAllByText('qwen-local · mlx · standard')).not.toHaveLength(0))
    const override = screen.getAllByRole('combobox', { name: /podcasts\.podcastModelPlan\.overrideModel/ })[0]
    expect(Array.from(override.querySelectorAll('option')).map((option) => option.textContent)).toEqual(['podcasts.podcastModelPlan.automaticRoute', 'qwen-local', 'qwen-heavy'])
  })

  it('uses the shared Studio with an honest locked Phase 3 boundary', async () => {
    render(<KnowledgePodcastPane seedDocumentIds={['knowledge_engine_document:plan']} />)

    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'podcasts.podcastStudio.title' })).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'podcasts.researchSetPanel.title' })).toBeInTheDocument()
      expect(screen.getByText('podcasts.productionTimeline.stageEvidence')).toBeInTheDocument()
      expect(screen.getAllByText('podcasts.productionTimeline.lockedDetail')).toHaveLength(2)
    })
  })
})

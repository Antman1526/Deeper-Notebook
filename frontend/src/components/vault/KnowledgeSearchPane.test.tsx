import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { LocalModelSettings, ModelRoutePlan } from '@/lib/api/local-models'

const indexedSearch = vi.hoisted(() => ({
  calls: [] as unknown[][],
  runSemanticSearch: vi.fn(),
  text: { data: undefined, isLoading: false, isError: false },
  semantic: { data: undefined, isPending: false, isError: false },
}))
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

vi.mock('@/lib/hooks/use-knowledge-command-data', () => ({
  useKnowledgeIndexedSearch: (...args: unknown[]) => {
    indexedSearch.calls.push(args)
    return indexedSearch
  },
}))
vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelSettings: () => savedSettings,
  useModelRoutePlan: (...args: unknown[]) => { routePlanCalls.push(args); return routePlan },
}))

import { KnowledgeSearchPane } from './KnowledgeSearchPane'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'

describe('KnowledgeSearchPane', () => {
  beforeEach(() => {
    routePlan.data = undefined
    routePlan.isError = false
    routePlan.isLoading = false
    routePlanCalls.length = 0
    savedSettings.data = localSettings()
    indexedSearch.calls = []
    indexedSearch.runSemanticSearch.mockReset()
    usePodcastStudioStore.getState().dismiss()
  })

  it('permits an empty current selection and does not start a search when opened', () => {
    render(<KnowledgeSearchPane query="" searchMode="text" spaceIds={[]} authorityKinds={[]} />)

    expect(indexedSearch.calls).toContainEqual(['', false, {
      mode: 'text', spaceIds: [], authorityKinds: [], tags: [],
    }])
    expect(indexedSearch.runSemanticSearch).not.toHaveBeenCalled()
  })

  it('submits semantic search only after the user asks for it', () => {
    render(<KnowledgeSearchPane query="research" searchMode="semantic" spaceIds={[]} authorityKinds={[]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Search knowledge' }))

    expect(indexedSearch.runSemanticSearch).toHaveBeenCalledOnce()
  })

  it('shows the active Embedding route without starting semantic search', () => {
    routePlan.data = { role: 'embedding_retrieval', outcome: 'ready', selected_model_id: 'nomic-local', selected_provider: 'ollama', resource_tier: 'light', selection_source: 'automatic', route_reason: 'Verified local route.', escalation_model_ids: [], blocked_reason: null, selected_fingerprint: 'fingerprint', selected_measurements: {} }
    render(<KnowledgeSearchPane query="" searchMode="text" spaceIds={[]} authorityKinds={[]} />)
    expect(screen.getByText('Embedding route')).toBeInTheDocument()
    expect(indexedSearch.runSemanticSearch).not.toHaveBeenCalled()
  })

  it('plans Embedding with saved Local Preferred settings and its explicit override', () => {
    savedSettings.data = localSettings({
      execution_policy: 'local_preferred',
      compute_profile: 'maximum_quality',
      role_overrides: { embedding_retrieval: 'embed-override' },
    })
    render(<KnowledgeSearchPane query="" searchMode="text" spaceIds={[]} authorityKinds={[]} />)
    expect(routePlanCalls).toContainEqual([{ role: 'embedding_retrieval', execution_policy: 'local_preferred', compute_profile: 'maximum_quality', role_override_model_id: 'embed-override', modalities: ['text'] }])
  })

  it('opens a text search as a review-only saved-search selection', () => {
    render(<KnowledgeSearchPane query="research plan" searchMode="text" spaceIds={['knowledge_engine_space:research']} authorityKinds={['external_read_only']} />)

    fireEvent.click(screen.getByRole('button', { name: 'Turn into podcast' }))

    expect(usePodcastStudioStore.getState()).toMatchObject({
      isOpen: true,
      destination: 'quick',
      selections: [{
        kind: 'saved_search', query: 'research plan', searchMode: 'text',
        spaceIds: ['knowledge_engine_space:research'], authorityKinds: ['external_read_only'],
      }],
    })
  })

  it('keeps a semantic search action visible but disabled until its unified embedding index is verified', () => {
    render(<KnowledgeSearchPane query="research" searchMode="semantic" spaceIds={[]} authorityKinds={[]} />)

    expect(screen.getByRole('button', { name: 'Turn into podcast' })).toBeDisabled()
    expect(screen.getByText('Semantic podcast selection needs a verified unified embedding index.')).toBeVisible()
  })
})

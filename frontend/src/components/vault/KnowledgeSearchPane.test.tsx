import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const indexedSearch = vi.hoisted(() => ({
  calls: [] as unknown[][],
  runSemanticSearch: vi.fn(),
  text: { data: undefined, isLoading: false, isError: false },
  semantic: { data: undefined, isPending: false, isError: false },
}))
const routePlan = vi.hoisted(() => ({ data: undefined as any, isError: false, isLoading: false }))

vi.mock('@/lib/hooks/use-knowledge-command-data', () => ({
  useKnowledgeIndexedSearch: (...args: unknown[]) => {
    indexedSearch.calls.push(args)
    return indexedSearch
  },
}))
vi.mock('@/lib/hooks/use-local-models', () => ({ useModelRoutePlan: () => routePlan }))

import { KnowledgeSearchPane } from './KnowledgeSearchPane'

describe('KnowledgeSearchPane', () => {
  beforeEach(() => {
    routePlan.data = undefined
    routePlan.isError = false
    routePlan.isLoading = false
    indexedSearch.calls = []
    indexedSearch.runSemanticSearch.mockReset()
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
})

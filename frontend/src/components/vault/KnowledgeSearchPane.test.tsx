import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const indexedSearch = vi.hoisted(() => ({
  calls: [] as unknown[][],
  runSemanticSearch: vi.fn(),
  text: { data: undefined, isLoading: false, isError: false },
  semantic: { data: undefined, isPending: false, isError: false },
}))

vi.mock('@/lib/hooks/use-knowledge-command-data', () => ({
  useKnowledgeIndexedSearch: (...args: unknown[]) => {
    indexedSearch.calls.push(args)
    return indexedSearch
  },
}))

import { KnowledgeSearchPane } from './KnowledgeSearchPane'

describe('KnowledgeSearchPane', () => {
  beforeEach(() => {
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
})

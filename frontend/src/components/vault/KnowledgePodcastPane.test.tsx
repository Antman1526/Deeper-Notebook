import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

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
})

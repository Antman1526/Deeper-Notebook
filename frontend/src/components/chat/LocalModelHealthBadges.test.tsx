import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LocalModelHealthBadges } from './LocalModelHealthBadges'

vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelsHealth: () => ({
    data: {
      overall: 'healthy',
      models: [
        { name: 'Local GGUF', status: 'healthy', detail: 'Hermes-3', latency_ms: 12 },
        { name: 'Local Embeddings', status: 'healthy', detail: 'nomic-embed', latency_ms: 8 },
      ],
    },
    isLoading: false,
  }),
}))

const qc = new QueryClient()

describe('LocalModelHealthBadges', () => {
  it('renders one badge per model', () => {
    render(
      <QueryClientProvider client={qc}>
        <LocalModelHealthBadges />
      </QueryClientProvider>
    )
    expect(screen.getByText(/Local GGUF/)).toBeInTheDocument()
    expect(screen.getByText(/Local Embeddings/)).toBeInTheDocument()
  })
})

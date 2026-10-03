import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LocalModelHealthBadges } from './LocalModelHealthBadges'

// The status label is interpolated, so this suite needs a t() that fills {{placeholders}}
// (the global setup mock returns the bare key).
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { name?: string; status?: string }) =>
      key === 'chat.localModelHealthBadges.statusAria' ? `${options?.name}: ${options?.status}` : key,
  }),
}))

vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelsHealth: () => ({
    data: {
      overall: 'healthy',
      models: [
        { name: 'Local GGUF', status: 'healthy', detail: 'Hermes-3', latency_ms: 12 },
        { name: 'Local Embeddings', status: 'unhealthy', detail: 'connection failed', latency_ms: null },
        { name: 'Not Configured', status: 'not_configured', detail: null, latency_ms: null },
      ],
    },
    isLoading: false,
  }),
}))

const qc = new QueryClient()

describe('LocalModelHealthBadges', () => {
  it('renders one badge per model with i18n status keys', () => {
    render(
      <QueryClientProvider client={qc}>
        <LocalModelHealthBadges />
      </QueryClientProvider>
    )
    expect(screen.getByText(/Local GGUF/)).toBeInTheDocument()
    expect(screen.getByText(/Local Embeddings/)).toBeInTheDocument()
    expect(screen.getByText(/Not Configured/)).toBeInTheDocument()
  })

  it('applies correct status dot classes based on model status', () => {
    const { container } = render(
      <QueryClientProvider client={qc}>
        <LocalModelHealthBadges />
      </QueryClientProvider>
    )
    // Check that status dots have correct Tailwind classes
    const dots = container.querySelectorAll('.h-2.w-2.rounded-full')
    expect(dots).toHaveLength(3)
    expect(dots[0]).toHaveClass('bg-success') // healthy
    expect(dots[1]).toHaveClass('bg-destructive') // unhealthy
    expect(dots[2]).toHaveClass('bg-muted-foreground/70') // not_configured (v0.8.0 — WCAG AA contrast bump)
  })

  it('includes aria-label with model name and status key', () => {
    render(
      <QueryClientProvider client={qc}>
        <LocalModelHealthBadges />
      </QueryClientProvider>
    )
    // Note: t() is mocked above to return the key string (with the aria template filled in)
    expect(screen.getByLabelText(/Local GGUF: models\.status\.healthy/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Local Embeddings: models\.status\.unhealthy/)).toBeInTheDocument()
  })
})

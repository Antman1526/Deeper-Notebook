import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LocalModelHealthBadges } from './LocalModelHealthBadges'

// The status label is interpolated, so this suite needs a t() that fills {{placeholders}}
// (the global setup mock returns the bare key).
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { name?: string; status?: string }) => {
      if (key === 'chat.localModelHealthBadges.statusAria') return `${options?.name}: ${options?.status}`
      // v0.8.130 — a non-English template, to prove auto-registered names are translated for display.
      if (key === 'models.localCredential.named') return `${options?.name} (lokal)`
      return key
    },
  }),
}))

// v0.8.130 — extra rows a single test can add; empty for every other test.
const extraModels = vi.hoisted(() => [] as Array<{ name: string; status: string; detail: string | null; latency_ms: number | null }>)

vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelsHealth: () => ({
    data: {
      overall: 'healthy',
      models: [
        { name: 'Local GGUF', status: 'healthy', detail: 'Hermes-3', latency_ms: 12 },
        { name: 'Local Embeddings', status: 'unhealthy', detail: 'connection failed', latency_ms: null },
        { name: 'Not Configured', status: 'not_configured', detail: null, latency_ms: null },
        ...extraModels,
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

  // v0.8.130 — the stored name stays English ("Whisper (local)"); only the label is translated.
  it('translates an auto-registered local credential name in the text and the aria-label', () => {
    extraModels.push({ name: 'Whisper (local)', status: 'healthy', detail: null, latency_ms: 5 })
    try {
      render(
        <QueryClientProvider client={qc}>
          <LocalModelHealthBadges />
        </QueryClientProvider>
      )
      expect(screen.getByText('Whisper (lokal)')).toBeInTheDocument()
      expect(screen.queryByText('Whisper (local)')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Whisper (lokal): models.status.healthy')).toBeInTheDocument()
    } finally {
      extraModels.length = 0
    }
  })
})

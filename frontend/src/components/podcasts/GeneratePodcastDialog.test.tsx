import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GeneratePodcastDialog } from './GeneratePodcastDialog'

const mutateAsync = vi.fn()

vi.mock('@/lib/hooks/use-notebooks', () => ({
  useNotebooks: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/lib/hooks/use-podcasts', () => ({
  useEpisodeProfiles: () => ({
    episodeProfiles: [{
      id: 'episode:one', name: 'Local overview', description: '',
      speaker_config: 'Local voices', default_briefing: 'Grounded', num_segments: 5,
    }],
    isLoading: false,
  }),
  useGeneratePodcast: () => ({ mutateAsync, isPending: false }),
}))

vi.mock('@/lib/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <GeneratePodcastDialog open onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  )
}

describe('GeneratePodcastDialog Audio Overview formats', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers the complete closed overview-format menu', () => {
    renderDialog()

    fireEvent.click(screen.getByRole('combobox', { name: 'Audio overview format' }))

    expect(screen.getAllByText('Deep Dive')).toHaveLength(2)
    expect(screen.getByText('Brief')).toBeInTheDocument()
    expect(screen.getByText('Critique')).toBeInTheDocument()
    expect(screen.getByText('Debate')).toBeInTheDocument()
  })

  it('resets the closed format selection when the dialog closes', () => {
    const onOpenChange = vi.fn()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <GeneratePodcastDialog open onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    )
    fireEvent.click(screen.getByRole('combobox', { name: 'Audio overview format' }))
    fireEvent.click(screen.getByText('Debate'))

    rerender(
      <QueryClientProvider client={client}>
        <GeneratePodcastDialog open={false} onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    )
    rerender(
      <QueryClientProvider client={client}>
        <GeneratePodcastDialog open onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    )

    expect(screen.getByRole('combobox', { name: 'Audio overview format' })).toHaveTextContent('Deep Dive')
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PodcastEpisode } from '@/lib/types/podcasts'
import { EpisodesTab } from './EpisodesTab'

const openModal = vi.fn()
const retryMutation = { isPending: false, mutateAsync: vi.fn(async () => undefined) }

const episode: PodcastEpisode = {
  id: 'episode:source-navigation',
  name: 'Source navigation episode',
  episode_profile: { id: 'episode-profile:source-navigation', name: 'Local', description: '', speaker_config: 'Local voice', default_briefing: '', num_segments: 3 },
  speaker_profile: { id: 'speaker-profile:source-navigation', name: 'Local voice', description: '', speakers: [] },
  briefing: '',
  job_status: 'completed',
  transcript_segments: [{ start_seconds: 0, end_seconds: 15, speaker: 'Host', text: 'A cited finding.', citation_ids: ['source:source-123'] }],
}
let currentEpisode = episode

vi.mock('@/lib/hooks/use-modal-manager', () => ({
  useModalManager: () => ({ openModal }),
}))

vi.mock('@/lib/api/podcasts', () => ({
  resolvePodcastAssetUrl: vi.fn(() => new Promise<string | null>(() => undefined)),
}))

vi.mock('@/lib/hooks/use-podcasts', () => ({
  usePodcastEpisodes: () => ({
    episodes: [currentEpisode],
    statusCounts: { total: 1, running: 0, completed: 1, failed: 0, pending: 0 },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    isFetching: false,
  }),
  useDeletePodcastEpisode: () => ({ isPending: false, mutateAsync: vi.fn(async () => undefined) }),
  useRetryPodcastEpisode: () => retryMutation,
  useCancelPodcastEpisode: () => ({ isPending: false, mutateAsync: vi.fn(async () => undefined), mutate: vi.fn() }),
  useApproveEpisodeOutline: () => ({ isPending: false, mutateAsync: vi.fn(async () => undefined) }),
  useUpdateEpisodeOutline: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn(async () => undefined) }),
}))

vi.mock('@/components/podcasts/GeneratePodcastDialog', () => ({
  GeneratePodcastDialog: () => null,
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string) => key, language: 'en-US' }),
}))

function renderTab() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EpisodesTab />
    </QueryClientProvider>,
  )
}

describe('EpisodesTab', () => {
  beforeEach(() => {
    openModal.mockClear()
    retryMutation.isPending = false
    currentEpisode = episode
  })

  it('opens the existing source modal from an exact source citation through the Library and Episode Lab', () => {
    renderTab()

    fireEvent.click(screen.getByRole('button', { name: 'Open Episode Lab for Source navigation episode' }))
    fireEvent.click(screen.getByRole('button', { name: 'source:source-123' }))

    expect(openModal).toHaveBeenCalledWith('source', 'source:source-123')
  })

  it('passes the parent retry mutation pending state through the Library to EpisodeCard', () => {
    retryMutation.isPending = true
    renderTab()

    expect(screen.getByRole('button', { name: 'podcasts.regenerating' })).toBeDisabled()
  })

  it('keeps the compact episode header controls inside the available width', () => {
    renderTab()

    expect(screen.getByRole('heading', { name: 'podcasts.overviewTitle' }).parentElement)
      .toHaveClass('min-w-0', 'max-w-full')
    expect(screen.getByRole('button', { name: 'common.refresh' }).parentElement)
      .toHaveClass('w-full', 'min-w-0', 'max-w-full')
  })

  it('keeps Lab retry disabled while a parent-started retry is pending', () => {
    currentEpisode = { ...episode, job_status: 'failed' }
    retryMutation.isPending = true
    renderTab()

    fireEvent.click(screen.getByRole('button', { name: 'Open Episode Lab for Source navigation episode' }))

    expect(screen.getByRole('button', { name: 'Retrying episode…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Retrying episode…' })).toHaveAttribute('aria-busy', 'true')
  })
})

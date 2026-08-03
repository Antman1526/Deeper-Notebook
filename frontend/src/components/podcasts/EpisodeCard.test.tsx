import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { EpisodeCard } from './EpisodeCard'
import type { PodcastEpisode } from '@/lib/types/podcasts'

vi.mock('@/lib/api/podcasts', () => ({
  resolvePodcastAssetUrl: vi.fn(async () => null),
}))

vi.mock('@/lib/hooks/use-podcasts', () => ({
  useApproveEpisodeOutline: () => ({ isPending: false, mutateAsync: vi.fn(async () => undefined) }),
  useCancelPodcastEpisode: () => ({ isPending: false, mutate: vi.fn() }),
  useUpdateEpisodeOutline: () => ({ isPending: false, mutate: vi.fn(), mutateAsync: vi.fn(async () => undefined) }),
}))

function createEpisode(overrides: Partial<PodcastEpisode> = {}): PodcastEpisode {
  return {
    id: 'episode:guarded',
    name: 'Guarded episode',
    episode_profile: {
      id: 'episode-profile:guarded',
      name: 'Local',
      description: '',
      speaker_config: 'Local voice',
      default_briefing: '',
      num_segments: 2,
    },
    speaker_profile: {
      id: 'speaker-profile:guarded',
      name: 'Local voice',
      description: '',
      speakers: [],
    },
    briefing: '',
    ...overrides,
  }
}

function renderCard(episode: PodcastEpisode, props: { onDelete?: () => void; onRetry?: () => void } = {}) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EpisodeCard
        episode={episode}
        onDelete={props.onDelete ?? vi.fn()}
        onRetry={props.onRetry}
      />
    </QueryClientProvider>,
  )
}

describe('EpisodeCard guarded actions', () => {
  it('requires delete confirmation before invoking the destructive callback', () => {
    const onDelete = vi.fn()
    renderCard(createEpisode(), { onDelete })

    fireEvent.click(screen.getByRole('button', { name: /podcasts\.delete$/ }))
    expect(onDelete).not.toHaveBeenCalled()
    expect(screen.getByRole('alertdialog')).toBeVisible()

    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: /podcasts\.delete$/ }))
    expect(onDelete).toHaveBeenCalledWith('episode:guarded')
  })

  it('requires confirmation before retrying a completed episode', () => {
    const onRetry = vi.fn()
    renderCard(createEpisode({ job_status: 'completed', audio_url: '/api/podcasts/episode:guarded/audio' }), { onRetry })

    fireEvent.click(screen.getByRole('button', { name: 'podcasts.regenerate' }))
    expect(onRetry).not.toHaveBeenCalled()
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toBeVisible()

    fireEvent.click(within(dialog).getByRole('button', { name: 'podcasts.regenerate' }))
    expect(onRetry).toHaveBeenCalledWith('episode:guarded')
  })

  it('keeps the existing Review Outline action for awaiting-review episodes', () => {
    renderCard(createEpisode({ job_status: 'completed', generation_stage: 'awaiting_review', outline: { segments: [{ name: 'Opening', description: 'Frame the evidence.', size: 'short' }] } }))

    expect(screen.getByRole('button', { name: /podcasts\.reviewOutline/ })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: /podcasts\.reviewOutline/ }))
    expect(screen.getByRole('dialog')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'podcasts.reviewOutlineTitle' })).toBeVisible()
  })

  it('does not invoke destructive callbacks during mount or dialog dismissal', () => {
    const onDelete = vi.fn()
    const onRetry = vi.fn()
    renderCard(createEpisode({ job_status: 'completed' }), { onDelete, onRetry })

    expect(onDelete).not.toHaveBeenCalled()
    expect(onRetry).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /podcasts\.delete$/ }))
    fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'common.cancel' }))
    expect(onDelete).not.toHaveBeenCalled()
    expect(onRetry).not.toHaveBeenCalled()
  })
})

import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import type { PodcastEpisode } from '@/lib/types/podcasts'
import { filterEpisodesForLibrary, groupEpisodesForLibrary, PodcastLibrary } from './PodcastLibrary'

function createEpisode(
  id: string,
  jobStatus: PodcastEpisode['job_status'] = null,
  generationStage: PodcastEpisode['generation_stage'] = null,
  overrides: Partial<PodcastEpisode> = {},
): PodcastEpisode {
  return {
    id,
    name: id,
    episode_profile: {
      id: `episode-profile:${id}`,
      name: 'Local',
      description: '',
      speaker_config: 'Local voice',
      default_briefing: '',
      num_segments: 3,
    },
    speaker_profile: {
      id: `speaker-profile:${id}`,
      name: 'Local voice',
      description: '',
      speakers: [],
    },
    briefing: '',
    job_status: jobStatus,
    generation_stage: generationStage,
    ...overrides,
  }
}

describe('groupEpisodesForLibrary', () => {
  it('separates current production, outline review, completed, and failed episodes', () => {
    const episode = (id: string, jobStatus: PodcastEpisode['job_status'], generationStage?: string) => createEpisode(id, jobStatus, generationStage)
    const groups = groupEpisodesForLibrary([
      episode('running', 'running'), episode('review', 'completed', 'awaiting_review'),
      episode('done', 'completed'), episode('failed', 'failed'),
    ])

    expect(groups['Continue Production'].map(item => item.id)).toEqual(['running'])
    expect(groups['Ready to Review'].map(item => item.id)).toEqual(['review'])
    expect(groups.Completed.map(item => item.id)).toEqual(['done'])
    expect(groups['Needs Attention'].map(item => item.id)).toEqual(['failed'])
  })

  it('opens one episode in the dedicated Lab without replacing the production card', () => {
    const episode = createEpisode('episode:one', 'completed', null, {
      name: 'Local evidence review',
      transcript_segments: [],
    })
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PodcastLibrary episodes={[episode]} onDelete={vi.fn()} onRetry={vi.fn()} />
    </QueryClientProvider>)

    fireEvent.click(screen.getByRole('button', { name: 'Open Episode Lab for Local evidence review' }))

    const lab = screen.getByRole('region', { name: 'Episode Lab' })
    expect(lab).toBeVisible()
    expect(within(lab).getByText('Local evidence review')).toBeVisible()
  })

  it('filters by date and aggregate selection authority without exposing source paths', () => {
    const episodes = [
      createEpisode('external-recent', null, null, {
        name: 'External recent',
        created: '2026-07-30T12:00:00Z',
        selection_summary: { authority_counts: { external_read_only: 2 } },
      }),
      createEpisode('app-old', null, null, {
        name: 'App old',
        created: '2026-05-01T12:00:00Z',
        selection_summary: { authority_counts: { app_owned: 1 } },
      }),
    ]

    const filtered = filterEpisodesForLibrary(episodes, {
      format: 'all', profile: 'all', stage: 'all', date: 'seven_days', authority: 'external_read_only',
    }, new Date('2026-08-01T12:00:00Z'))

    expect(filtered.map(item => item.id)).toEqual(['external-recent'])
  })
})

import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { filterEpisodesForLibrary, groupEpisodesForLibrary, PodcastLibrary } from './PodcastLibrary'

describe('groupEpisodesForLibrary', () => {
  it('separates current production, outline review, completed, and failed episodes', () => {
    const episode = (id: string, job_status: any, generation_stage?: string) => ({ id, name: id, job_status, generation_stage, episode_profile: { name: 'Local', num_segments: 3 }, speaker_profile: {}, briefing: '' })
    const groups = groupEpisodesForLibrary([
      episode('running', 'running'), episode('review', 'completed', 'awaiting_review'),
      episode('done', 'completed'), episode('failed', 'failed'),
    ] as any)

    expect(groups['Continue Production'].map(item => item.id)).toEqual(['running'])
    expect(groups['Ready to Review'].map(item => item.id)).toEqual(['review'])
    expect(groups.Completed.map(item => item.id)).toEqual(['done'])
    expect(groups['Needs Attention'].map(item => item.id)).toEqual(['failed'])
  })

  it('opens one episode in the dedicated Lab without replacing the production card', () => {
    const episode = {
      id: 'episode:one', name: 'Local evidence review', job_status: 'completed',
      episode_profile: { name: 'Local', num_segments: 3 }, speaker_profile: {}, briefing: '',
      transcript_segments: [],
    }
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PodcastLibrary episodes={[episode] as any} onDelete={vi.fn()} onRetry={vi.fn()} />
    </QueryClientProvider>)

    fireEvent.click(screen.getByRole('button', { name: 'Open Episode Lab for Local evidence review' }))

    const lab = screen.getByRole('region', { name: 'Episode Lab' })
    expect(lab).toBeVisible()
    expect(within(lab).getByText('Local evidence review')).toBeVisible()
  })

  it('filters by date and aggregate selection authority without exposing source paths', () => {
    const episodes = [
      { id: 'external-recent', name: 'External recent', created: '2026-07-30T12:00:00Z', selection_summary: { authority_counts: { external_read_only: 2 } } },
      { id: 'app-old', name: 'App old', created: '2026-05-01T12:00:00Z', selection_summary: { authority_counts: { app_owned: 1 } } },
    ] as any

    const filtered = filterEpisodesForLibrary(episodes, {
      format: 'all', profile: 'all', stage: 'all', date: 'seven_days', authority: 'external_read_only',
    }, new Date('2026-08-01T12:00:00Z'))

    expect(filtered.map(item => item.id)).toEqual(['external-recent'])
  })
})

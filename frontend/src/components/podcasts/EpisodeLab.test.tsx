import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EpisodeLab, getEpisodeStageHistory, isExactSourceCitationId } from './EpisodeLab'
import { useAudioPlayerStore } from '@/lib/stores/audio-player-store'
import type { PodcastEpisode } from '@/lib/types/podcasts'

const episode: PodcastEpisode = {
  id: 'episode:local-review',
  name: 'Local evidence review',
  episode_profile: { id: 'episode-profile:local', name: 'Local', description: '', speaker_config: 'Local voice', default_briefing: '', num_segments: 3 },
  speaker_profile: { id: 'speaker-profile:local', name: 'Local voice', description: '', speakers: [] },
  briefing: 'A source-grounded local overview.',
  audio_url: '/api/podcasts/episodes/episode:local-review/audio',
  generation_stage: 'generating_audio',
  outline: {
    segments: [{ name: 'Opening finding', description: 'Frame the evidence.', size: 'short' }],
  },
  transcript_segments: [{ start_seconds: 15, end_seconds: 30, speaker: 'Host', text: 'A reviewed finding.', citation_ids: ['citation:one'] }],
}

describe('EpisodeLab', () => {
  beforeEach(() => {
    useAudioPlayerStore.setState({ episode: null, positionByEpisode: {}, requestedPlayback: false })
  })

  it('moves a completed local episode into the route-persistent player', () => {
    render(<EpisodeLab episode={episode} onClose={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'podcasts.episodeLab.playInGlobalPlayer' }))

    expect(useAudioPlayerStore.getState().episode).toMatchObject({
      id: 'episode:local-review',
      title: 'Local evidence review',
      sourcePath: '/api/podcasts/episodes/episode:local-review/audio',
    })
  })

  it('keeps citation mapping honest and exposes only explicit episode actions', () => {
    const onRetry = vi.fn()
    render(<EpisodeLab episode={{ ...episode, job_status: 'failed' }} onClose={vi.fn()} onRetry={onRetry} />)

    fireEvent.click(screen.getByRole('button', { name: 'citation:one' }))
    expect(screen.getByText('podcasts.episodeLab.claimCitationUnavailable')).toBeVisible()
    // Internal roadmap labels are not user-facing copy.
    expect(document.body).not.toHaveTextContent(/Phase[- ]\d/)

    fireEvent.click(screen.getByRole('button', { name: 'podcasts.episodeLab.retry' }))
    expect(onRetry).toHaveBeenCalledWith('episode:local-review')
    expect(screen.queryByRole('button', { name: 'podcasts.episodeLab.cancel' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'podcasts.episodeLab.downloadAudio' })).toHaveAttribute('download')
  })

  it('renders the read-only current outline and persisted stage history with locked Phase 3 stages', () => {
    const completed = { ...episode, job_status: 'completed' as const, generation_stage: null, audio_file: '/private/audio.mp3' }
    render(<EpisodeLab episode={completed} onClose={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'podcasts.episodeLab.currentOutline' })).toBeVisible()
    expect(screen.getByText('Opening finding')).toBeVisible()
    expect(screen.getByText('Frame the evidence.')).toBeVisible()
    expect(screen.getByText('short')).toBeVisible()
    expect(screen.getByText('podcasts.episodeLab.stage.outlinePresent')).toBeVisible()
    expect(screen.getByText('podcasts.episodeLab.stage.transcriptPresent')).toBeVisible()
    expect(screen.getByText('podcasts.episodeLab.stage.audioPresent')).toBeVisible()
    expect(screen.getByText('podcasts.episodeLab.stage.completed')).toBeVisible()
    expect(screen.getAllByText('podcasts.episodeLab.lockedStageCopy')).toHaveLength(2)

    expect(getEpisodeStageHistory(completed).map(item => item.labelKey)).toEqual([
      'podcasts.episodeLab.stage.created',
      'podcasts.episodeLab.stage.outlinePresent',
      'podcasts.episodeLab.stage.transcriptPresent',
      'podcasts.episodeLab.stage.audioPresent',
      'podcasts.episodeLab.stage.completed',
    ])
  })

  it('shows an honest outline empty state and cancelled current stage', () => {
    render(<EpisodeLab episode={{ ...episode, outline: null, transcript_segments: [], audio_url: null, audio_file: null, job_status: 'completed', generation_stage: 'cancelled' }} onClose={vi.fn()} />)

    expect(screen.getByText('podcasts.episodeLab.noOutline')).toBeVisible()
    expect(screen.getByText('podcasts.episodeLab.stage.cancelled')).toBeVisible()
    expect(screen.queryByText('podcasts.episodeLab.stage.transcriptPresent')).not.toBeInTheDocument()
    expect(screen.queryByText('podcasts.episodeLab.stage.audioPresent')).not.toBeInTheDocument()
  })

  it('marks exactly one persisted stage as current and gives failures precedence', () => {
    const review = getEpisodeStageHistory({ ...episode, job_status: 'completed', generation_stage: 'awaiting_review' })
    expect(review.filter(item => item.current).map(item => item.labelKey)).toEqual(['podcasts.episodeLab.stage.awaitingOutlineReview'])
    expect(review.map(item => item.labelKey)).not.toContain('podcasts.episodeLab.stage.completed')

    const failed = getEpisodeStageHistory({ ...episode, job_status: 'failed', generation_stage: 'generating_audio' })
    expect(failed.filter(item => item.current).map(item => item.labelKey)).toEqual(['podcasts.episodeLab.stage.failed'])

    const onlyCreated = getEpisodeStageHistory({ ...episode, outline: null, transcript_segments: [], audio_url: null, audio_file: null, job_status: null, generation_stage: null })
    expect(onlyCreated.filter(item => item.current).map(item => item.labelKey)).toEqual(['podcasts.episodeLab.stage.created'])

    const { container } = render(<EpisodeLab episode={{ ...episode, job_status: 'completed', generation_stage: 'awaiting_review' }} onClose={vi.fn()} />)
    expect(container.querySelectorAll('[aria-current="step"]')).toHaveLength(1)
    expect(screen.getByText('podcasts.episodeLab.stage.awaitingOutlineReview')).toBeVisible()
    expect(screen.queryByText('podcasts.episodeLab.stage.completed')).not.toBeInTheDocument()
  })

  it('subscribes to the shared playback position and seeks through the shared store', () => {
    render(<EpisodeLab episode={episode} onClose={vi.fn()} />)

    const transcript = screen.getByText('A reviewed finding.').closest('article')
    expect(transcript).not.toHaveClass('border-primary')

    act(() => {
      useAudioPlayerStore.getState().setPosition('episode:local-review', 20)
    })
    expect(transcript).toHaveClass('border-primary')

    fireEvent.click(screen.getByRole('button', { name: '0:15 Host' }))
    expect(useAudioPlayerStore.getState().positionByEpisode['episode:local-review']).toBe(15)
  })

  it('routes only bounded source citations to the optional callback and uses the not-yet-available notice otherwise', () => {
    const onCitationClick = vi.fn()
    const sourceEpisode = {
      ...episode,
      transcript_segments: [{ ...episode.transcript_segments![0], citation_ids: ['source:source-123'] }],
    }
    const { rerender } = render(<EpisodeLab episode={sourceEpisode} onClose={vi.fn()} onCitationClick={onCitationClick} />)

    fireEvent.click(screen.getByRole('button', { name: 'source:source-123' }))
    expect(onCitationClick).toHaveBeenCalledWith('source:source-123')
    expect(screen.queryByText('podcasts.episodeLab.claimCitationUnavailable')).not.toBeInTheDocument()

    rerender(<EpisodeLab episode={episode} onClose={vi.fn()} onCitationClick={onCitationClick} />)
    fireEvent.click(screen.getByRole('button', { name: 'citation:one' }))
    expect(onCitationClick).toHaveBeenCalledTimes(1)
    expect(screen.getByText('podcasts.episodeLab.claimCitationUnavailable')).toBeVisible()
  })

  it('accepts only the bounded SourceId citation contract', () => {
    expect(isExactSourceCitationId('source:source-123_abc')).toBe(true)
    expect(isExactSourceCitationId(`source:${'a'.repeat(121)}`)).toBe(true)
    expect(isExactSourceCitationId('source:source:123')).toBe(false)
    expect(isExactSourceCitationId(`source:${'a'.repeat(122)}`)).toBe(false)
  })

  it('downloads only contained API-relative audio URLs', () => {
    const { rerender } = render(<EpisodeLab episode={episode} onClose={vi.fn()} />)
    expect(screen.getByRole('link', { name: 'podcasts.episodeLab.downloadAudio' })).toHaveAttribute('href', '/api/podcasts/episodes/episode:local-review/audio')

    for (const audio of [
      '/Users/Antman/private.mp3',
      'https://example.com/audio.mp3',
      'file:///tmp/audio.mp3',
      '/api/anything',
      '/api/podcasts/episodes/../audio',
      '/api/podcasts/episodes/episode:local-review/audio?download=1',
    ]) {
      rerender(<EpisodeLab episode={{ ...episode, audio_url: audio }} onClose={vi.fn()} />)
      expect(screen.getByRole('button', { name: 'podcasts.episodeLab.downloadAudio' })).toBeDisabled()
    }

    rerender(<EpisodeLab episode={{ ...episode, audio_url: null, audio_file: '/private/audio.mp3' }} onClose={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'podcasts.episodeLab.downloadAudio' })).toBeDisabled()
  })

  it('does not bypass the card confirmation path for completed episodes', () => {
    render(<EpisodeLab episode={{ ...episode, job_status: 'completed' }} onClose={vi.fn()} onRetry={vi.fn()} onCancel={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'podcasts.episodeLab.retry' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'podcasts.episodeLab.cancel' })).not.toBeInTheDocument()
  })

  it('only exposes cancellation while a generation is active', () => {
    const onCancel = vi.fn()
    render(<EpisodeLab episode={{ ...episode, job_status: 'running' }} onClose={vi.fn()} onCancel={onCancel} />)

    fireEvent.click(screen.getByRole('button', { name: 'podcasts.episodeLab.cancel' }))
    expect(onCancel).toHaveBeenCalledWith('episode:local-review')
  })

  it('fences repeated retries while the asynchronous retry is pending', async () => {
    let resolveRetry: (() => void) | undefined
    const onRetry = vi.fn(() => new Promise<void>((resolve) => { resolveRetry = resolve }))
    render(<EpisodeLab episode={{ ...episode, job_status: 'failed' }} onClose={vi.fn()} onRetry={onRetry} />)

    fireEvent.click(screen.getByRole('button', { name: 'podcasts.episodeLab.retry' }))
    fireEvent.click(screen.getByRole('button', { name: 'podcasts.episodeLab.retrying' }))

    expect(onRetry).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'podcasts.episodeLab.retrying' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'podcasts.episodeLab.retrying' })).toHaveAttribute('aria-busy', 'true')

    await act(async () => { resolveRetry?.() })
    await waitFor(() => expect(screen.getByRole('button', { name: 'podcasts.episodeLab.retry' })).toBeEnabled())
  })

  it('fences repeated cancellations while the asynchronous cancellation is pending', async () => {
    let resolveCancel: (() => void) | undefined
    const onCancel = vi.fn(() => new Promise<void>((resolve) => { resolveCancel = resolve }))
    render(<EpisodeLab episode={{ ...episode, job_status: 'running' }} onClose={vi.fn()} onCancel={onCancel} />)

    fireEvent.click(screen.getByRole('button', { name: 'podcasts.episodeLab.cancel' }))
    fireEvent.click(screen.getByRole('button', { name: 'podcasts.episodeLab.cancelling' }))

    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'podcasts.episodeLab.cancelling' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'podcasts.episodeLab.cancelling' })).toHaveAttribute('aria-busy', 'true')

    await act(async () => { resolveCancel?.() })
    await waitFor(() => expect(screen.getByRole('button', { name: 'podcasts.episodeLab.cancel' })).toBeEnabled())
  })
})

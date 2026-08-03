import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EpisodeLab } from './EpisodeLab'
import { useAudioPlayerStore } from '@/lib/stores/audio-player-store'
import type { PodcastEpisode } from '@/lib/types/podcasts'

const episode: PodcastEpisode = {
  id: 'episode:local-review',
  name: 'Local evidence review',
  episode_profile: { id: 'episode-profile:local', name: 'Local', description: '', speaker_config: 'Local voice', default_briefing: '', num_segments: 3 },
  speaker_profile: { id: 'speaker-profile:local', name: 'Local voice', description: '', speakers: [] },
  briefing: 'A source-grounded local overview.',
  audio_url: '/api/podcasts/episode:local-review/audio',
  generation_stage: 'generating_audio',
  transcript_segments: [{ start_seconds: 15, end_seconds: 30, speaker: 'Host', text: 'A reviewed finding.', citation_ids: ['citation:one'] }],
}

describe('EpisodeLab', () => {
  beforeEach(() => {
    useAudioPlayerStore.setState({ episode: null, positionByEpisode: {}, requestedPlayback: false })
  })

  it('moves a completed local episode into the route-persistent player', () => {
    render(<EpisodeLab episode={episode} onClose={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Play in global player' }))

    expect(useAudioPlayerStore.getState().episode).toMatchObject({
      id: 'episode:local-review',
      title: 'Local evidence review',
      sourcePath: '/api/podcasts/episode:local-review/audio',
    })
  })

  it('keeps citation mapping honest and exposes only explicit episode actions', () => {
    const onRetry = vi.fn()
    render(<EpisodeLab episode={{ ...episode, job_status: 'failed' }} onClose={vi.fn()} onRetry={onRetry} />)

    fireEvent.click(screen.getByRole('button', { name: 'citation:one' }))
    expect(screen.getByText('Source citation — claim evidence mapping arrives in Phase 3')).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'Retry episode' }))
    expect(onRetry).toHaveBeenCalledWith('episode:local-review')
    expect(screen.queryByRole('button', { name: 'Cancel episode' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download audio' })).toHaveAttribute('download')
  })

  it('does not bypass the card confirmation path for completed episodes', () => {
    render(<EpisodeLab episode={{ ...episode, job_status: 'completed' }} onClose={vi.fn()} onRetry={vi.fn()} onCancel={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'Retry episode' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel episode' })).not.toBeInTheDocument()
  })

  it('only exposes cancellation while a generation is active', () => {
    const onCancel = vi.fn()
    render(<EpisodeLab episode={{ ...episode, job_status: 'running' }} onClose={vi.fn()} onCancel={onCancel} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel episode' }))
    expect(onCancel).toHaveBeenCalledWith('episode:local-review')
  })
})

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GlobalAudioPlayer } from './GlobalAudioPlayer'
import { useAudioPlayerStore } from '@/lib/stores/audio-player-store'

vi.mock('@/lib/api/podcasts', () => ({
  resolvePodcastAssetUrl: vi.fn(async () => 'http://localhost/episode.mp3'),
}))

describe('GlobalAudioPlayer', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useAudioPlayerStore.setState({ episode: null, positionByEpisode: {}, requestedPlayback: false })
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn(() => Promise.resolve()) })
    Object.defineProperty(HTMLMediaElement.prototype, 'pause', { configurable: true, value: vi.fn() })
  })

  it('persists a selected episode and exposes transport controls', async () => {
    act(() => {
      useAudioPlayerStore.getState().setEpisode({
        id: 'episode:one',
        title: 'Local evidence review',
        sourcePath: '/api/podcasts/episode.mp3',
        transcriptSegments: [],
      })
    })
    render(<GlobalAudioPlayer />)

    expect(screen.getByLabelText('Audio overview player')).toBeInTheDocument()
    expect(screen.getByText('Local evidence review')).toBeInTheDocument()
    await waitFor(() => expect(document.querySelector('audio')?.src).toContain('episode.mp3'))

    fireEvent.click(screen.getByRole('button', { name: 'Stop overview' }))
    expect(useAudioPlayerStore.getState().episode).toBeNull()
  })
})

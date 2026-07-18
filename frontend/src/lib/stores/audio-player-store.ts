import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { TranscriptSegment } from '@/lib/types/podcasts'

export interface PlayingEpisode {
  id: string
  title: string
  sourcePath: string
  transcriptSegments: TranscriptSegment[]
}

interface AudioPlayerState {
  episode: PlayingEpisode | null
  positionByEpisode: Record<string, number>
  requestedPlayback: boolean
  setEpisode: (episode: PlayingEpisode) => void
  setPosition: (episodeId: string, seconds: number) => void
  requestPlayback: () => void
  pause: () => void
  clear: () => void
}

// Audio data stays in the browser's media element. Persisting only a path and
// resume position lets playback survive navigation without retaining content.
export const useAudioPlayerStore = create<AudioPlayerState>()(
  persist(
    (set) => ({
      episode: null,
      positionByEpisode: {},
      requestedPlayback: false,
      setEpisode: (episode) => set({ episode, requestedPlayback: true }),
      setPosition: (episodeId, seconds) =>
        set((state) => ({
          positionByEpisode: { ...state.positionByEpisode, [episodeId]: seconds },
        })),
      requestPlayback: () => set({ requestedPlayback: true }),
      pause: () => set({ requestedPlayback: false }),
      clear: () => set({ episode: null, requestedPlayback: false }),
    }),
    {
      name: 'onp-audio-player',
      partialize: (state) => ({
        episode: state.episode,
        positionByEpisode: state.positionByEpisode,
      }),
    },
  ),
)

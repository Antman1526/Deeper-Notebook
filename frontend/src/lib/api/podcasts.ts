import apiClient from './client'
import { getApiUrl } from '@/lib/config'
import {
  PodcastEpisode,
  EpisodeProfile,
  SpeakerProfile,
  Language,
  PodcastGenerationRequest,
  PodcastGenerationResponse,
  PodcastReadiness,
  PodcastSelectionPreview,
} from '@/lib/types/podcasts'
import {
  normalizePodcastSelections,
  toPodcastSelectionWire,
  type PodcastSelection,
} from '@/lib/podcasts/selection'

export type EpisodeProfileInput = Omit<EpisodeProfile, 'id'>
export type SpeakerProfileInput = Omit<SpeakerProfile, 'id'>

export async function resolvePodcastAssetUrl(path?: string | null): Promise<string | undefined> {
  if (!path) {
    return undefined
  }

  if (/^https?:\/\//i.test(path)) {
    return path
  }

  const base = await getApiUrl()

  if (path.startsWith('/')) {
    return `${base}${path}`
  }

  return `${base}/${path}`
}

export const podcastsApi = {
  previewPodcastSelection: async (selections: PodcastSelection[]) => {
    const response = await apiClient.post<PodcastSelectionPreview>(
      '/podcasts/selection/preview',
      { selections: normalizePodcastSelections(selections).map(toPodcastSelectionWire) },
    )
    return response.data
  },

  getPodcastReadiness: async (
    selections: PodcastSelection[],
    options: {
      executionPolicy?: 'strict_local' | 'local_preferred' | 'custom'
      computeProfile?: 'efficient' | 'balanced' | 'maximum_quality'
      includeTranscription?: boolean
    } = {},
  ) => {
    const response = await apiClient.post<PodcastReadiness>('/podcasts/readiness', {
      selections: normalizePodcastSelections(selections).map(toPodcastSelectionWire),
      execution_policy: options.executionPolicy ?? 'strict_local',
      compute_profile: options.computeProfile ?? 'balanced',
      include_transcription: options.includeTranscription ?? false,
    })
    return response.data
  },

  listEpisodes: async () => {
    const response = await apiClient.get<PodcastEpisode[]>('/podcasts/episodes')
    return response.data
  },

  deleteEpisode: async (episodeId: string) => {
    await apiClient.delete(`/podcasts/episodes/${episodeId}`)
  },

  retryEpisode: async (episodeId: string) => {
    const response = await apiClient.post<{ job_id: string; message: string }>(
      `/podcasts/episodes/${episodeId}/retry`
    )
    return response.data
  },

  // v0.8.68 — cancel an in-flight generation (worker polls the flag).
  cancelEpisode: async (episodeId: string) => {
    const response = await apiClient.post<{ message: string }>(
      `/podcasts/episodes/${episodeId}/cancel`
    )
    return response.data
  },

  // v0.8.68 — outline-review workflow.
  updateEpisodeOutline: async (
    episodeId: string,
    segments: import('@/lib/types/podcasts').OutlineSegment[],
  ) => {
    const response = await apiClient.put<{ message: string; outline: unknown }>(
      `/podcasts/episodes/${episodeId}/outline`,
      { segments }
    )
    return response.data
  },

  approveEpisodeOutline: async (episodeId: string) => {
    const response = await apiClient.post<{ job_id: string; message: string }>(
      `/podcasts/episodes/${episodeId}/approve-outline`
    )
    return response.data
  },

  listEpisodeProfiles: async () => {
    const response = await apiClient.get<EpisodeProfile[]>('/episode-profiles')
    return response.data
  },

  createEpisodeProfile: async (payload: EpisodeProfileInput) => {
    const response = await apiClient.post<EpisodeProfile>(
      '/episode-profiles',
      payload
    )
    return response.data
  },

  updateEpisodeProfile: async (profileId: string, payload: EpisodeProfileInput) => {
    const response = await apiClient.put<EpisodeProfile>(
      `/episode-profiles/${profileId}`,
      payload
    )
    return response.data
  },

  deleteEpisodeProfile: async (profileId: string) => {
    await apiClient.delete(`/episode-profiles/${profileId}`)
  },

  duplicateEpisodeProfile: async (profileId: string) => {
    const response = await apiClient.post<EpisodeProfile>(
      `/episode-profiles/${profileId}/duplicate`
    )
    return response.data
  },

  listSpeakerProfiles: async () => {
    const response = await apiClient.get<SpeakerProfile[]>('/speaker-profiles')
    return response.data
  },

  createSpeakerProfile: async (payload: SpeakerProfileInput) => {
    const response = await apiClient.post<SpeakerProfile>(
      '/speaker-profiles',
      payload
    )
    return response.data
  },

  updateSpeakerProfile: async (profileId: string, payload: SpeakerProfileInput) => {
    const response = await apiClient.put<SpeakerProfile>(
      `/speaker-profiles/${profileId}`,
      payload
    )
    return response.data
  },

  deleteSpeakerProfile: async (profileId: string) => {
    await apiClient.delete(`/speaker-profiles/${profileId}`)
  },

  duplicateSpeakerProfile: async (profileId: string) => {
    const response = await apiClient.post<SpeakerProfile>(
      `/speaker-profiles/${profileId}/duplicate`
    )
    return response.data
  },

  generatePodcast: async (payload: PodcastGenerationRequest) => {
    const response = await apiClient.post<PodcastGenerationResponse>(
      '/podcasts/generate',
      {
        // Make the new closed format explicit for callers compiled before
        // the dialog update; the backend keeps the same deep_dive default.
        ...payload,
        mode: payload.mode ?? 'deep_dive',
      }
    )
    return response.data
  },

  // v0.7.31 — heuristic auto-suggester. Given a notebook or list of
  // source IDs, returns recommended episode profile + length + title +
  // briefing addition. No LLM call; instant + deterministic.
  suggestEpisode: async (payload: {
    notebook_id?: string
    source_ids?: string[]
  }) => {
    const response = await apiClient.post<{
      episode_profile_name: string
      length_minutes: number
      title: string
      briefing_addition: string
      reasoning: string
      matched_signals: Record<string, number>
    }>('/podcasts/suggest', payload)
    return response.data
  },

  listLanguages: async () => {
    const response = await apiClient.get<Language[]>('/languages')
    return response.data
  },
}

import apiClient from './client'

export interface VideoOverviewComposeRequest {
  slide_deck_artifact_id: string
  podcast_episode_id: string
  caption_language?: string
}

export interface VideoOverview {
  artifact_id: string
  episode_id: string
  duration_seconds: number
  media_url: string
  captions_url: string
}

export const videoOverviewsApi = {
  compose: async (payload: VideoOverviewComposeRequest) => (
    await apiClient.post<VideoOverview>('/video-overviews', payload)
  ).data,
}

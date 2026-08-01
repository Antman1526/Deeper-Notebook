export type EpisodeStatus =
  | 'running'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'error'
  | 'pending'
  | 'submitted'
  | 'unknown'

export interface EpisodeProfile {
  id: string
  name: string
  description: string
  speaker_config: string
  outline_llm?: string | null
  transcript_llm?: string | null
  language?: string | null
  default_briefing: string
  num_segments: number
  // Legacy fields (app ignores, kept in DB for migration)
  outline_provider?: string | null
  outline_model?: string | null
  transcript_provider?: string | null
  transcript_model?: string | null
}

export interface SpeakerVoiceConfig {
  name: string
  voice_id: string
  backstory: string
  personality: string
  voice_model?: string | null
}

export interface SpeakerProfile {
  id: string
  name: string
  description: string
  voice_model?: string | null
  speakers: SpeakerVoiceConfig[]
  // Legacy fields
  tts_provider?: string | null
  tts_model?: string | null
}

export interface Language {
  code: string
  name: string
}

export interface PodcastEpisode {
  id: string
  name: string
  episode_profile: EpisodeProfile
  speaker_profile: SpeakerProfile
  briefing: string
  // v0.8.95 -- closed Audio Overview formats. Older episodes read as deep_dive.
  mode?: PodcastOverviewMode
  custom_prompt?: string | null
  audio_file?: string | null
  audio_url?: string | null
  transcript?: Record<string, unknown> | null
  outline?: Record<string, unknown> | null
  transcript_segments?: TranscriptSegment[]
  created?: string | null
  job_status?: EpisodeStatus | null
  error_message?: string | null
  // v0.8.68 — per-stage progress / outline-review state.
  generation_stage?: string | null
}

export type PodcastOverviewMode = 'deep_dive' | 'brief' | 'critique' | 'debate'

export interface TranscriptSegment {
  start_seconds: number
  end_seconds: number
  speaker: string
  text: string
  citation_ids: string[]
}

// v0.8.68 — outline shape for the review editor (mirrors podcast-creator).
export interface OutlineSegment {
  name: string
  description: string
  size: 'short' | 'medium' | 'long'
}

export interface PodcastGenerationRequest {
  episode_profile: string
  speaker_profile: string
  episode_name: string
  content?: string
  notebook_id?: string
  briefing_suffix?: string | null
  mode?: PodcastOverviewMode
  custom_prompt?: string | null
  // v0.8.86 — per-episode length (overrides the profile's segment count).
  episode_length?: 'short' | 'medium' | 'long'
  // v0.8.68 — stop after the outline for user review before audio.
  review_outline?: boolean
}

export interface PodcastGenerationResponse {
  job_id: string
  status: string
  message: string
  episode_profile: string
  episode_name: string
  mode: PodcastOverviewMode
}

export type PodcastSelectionAuthority = 'app_owned' | 'external_read_only'
export type PodcastSelectionState =
  | 'included'
  | 'duplicate'
  | 'unavailable'
  | 'changed'
  | 'empty'
  | 'failed_parse'
  | 'oversize'

export interface PodcastSelectionPreviewEntry {
  stableId: string
  title: string
  authorityKind: PodcastSelectionAuthority
  relativeLocator: string | null
  revisionId: string | null
  fingerprint: string | null
  state: PodcastSelectionState
  reason: string
  estimatedCharacters: number
}

export interface PodcastSelectionPreview {
  selectionFingerprint: string
  entries: PodcastSelectionPreviewEntry[]
  includedCharacters: number
  requiresBatchEngine: boolean
  currentWorkerEligible: boolean
  blockedReasons: string[]
}

export interface PodcastStageModelPlan {
  role: 'podcast_outline' | 'podcast_script' | 'text_to_speech' | 'speech_to_text'
  outcome: 'ready' | 'blocked' | 'approval_required'
  modelId: string | null
  provider: string | null
  resourceTier: 'light' | 'standard' | 'heavyweight' | null
  selectionSource: 'automatic' | 'role_override' | 'production_override' | null
  reason: string
  blockedReason: string | null
}

export interface PodcastReadiness {
  preview: PodcastSelectionPreview
  stagePlans: PodcastStageModelPlan[]
  ready: boolean
  blockedReasons: string[]
}

export interface PodcastStudioSubmitResponse {
  jobId: string
  status: 'submitted'
  message: string
  episodeProfile: string
  episodeName: string
  mode: PodcastOverviewMode
}

export type EpisodeStatusGroup = 'running' | 'completed' | 'failed' | 'pending'

export type EpisodeStatusGroups = Record<EpisodeStatusGroup, PodcastEpisode[]>

export const ACTIVE_EPISODE_STATUSES: EpisodeStatus[] = [
  'running',
  'processing',
  'pending',
  'submitted',
]

export const FAILED_EPISODE_STATUSES: EpisodeStatus[] = ['failed', 'error']

export function groupEpisodesByStatus(episodes: PodcastEpisode[]): EpisodeStatusGroups {
  return episodes.reduce<EpisodeStatusGroups>(
    (groups, episode) => {
      const status = episode.job_status || 'unknown'

      if (status === 'running' || status === 'processing') {
        groups.running.push(episode)
        return groups
      }

      if (status === 'completed') {
        groups.completed.push(episode)
        return groups
      }

      if (FAILED_EPISODE_STATUSES.includes(status)) {
        groups.failed.push(episode)
        return groups
      }

      groups.pending.push(episode)
      return groups
    },
    { running: [], completed: [], failed: [], pending: [] }
  )
}

export function speakerUsageMap(
  speakerProfiles: SpeakerProfile[] | undefined,
  episodeProfiles: EpisodeProfile[] | undefined
): Record<string, number> {
  if (!speakerProfiles || !episodeProfiles) {
    return {}
  }

  const usage: Record<string, number> = {}

  for (const profile of speakerProfiles) {
    usage[profile.name] = 0
  }

  for (const episodeProfile of episodeProfiles) {
    const key = episodeProfile.speaker_config
    if (key in usage) {
      usage[key] += 1
    }
  }

  return usage
}

/** Check if a profile needs model configuration (missing required model references) */
export function needsModelSetup(profile: EpisodeProfile | SpeakerProfile): boolean {
  if ('outline_llm' in profile) {
    const ep = profile as EpisodeProfile
    return !ep.outline_llm || !ep.transcript_llm
  }
  const sp = profile as SpeakerProfile
  return !sp.voice_model
}

import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./client', () => ({ default: { post: vi.fn() } }))

import apiClient from './client'
import { podcastsApi } from './podcasts'

describe('podcast Studio API', () => {
  beforeEach(() => vi.resetAllMocks())

  it('maps a redacted readiness wire response into the camelCase UI contract', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: {
      preview: {
        selection_fingerprint: 'a'.repeat(64),
        entries: [{
          stable_id: 'notebook:research', title: 'Research', authority_kind: 'app_owned',
          relative_locator: null, revision_id: null, fingerprint: 'b'.repeat(64),
          state: 'included', reason: 'included', estimated_characters: 40,
        }],
        included_characters: 40, requires_batch_engine: false,
        current_worker_eligible: true, blocked_reasons: [],
      },
      stage_plans: [{
        role: 'podcast_outline', outcome: 'ready', model_id: 'local-outline',
        provider: 'openai_compatible', resource_tier: 'light',
        selection_source: 'automatic', reason: 'verified', blocked_reason: null,
      }],
      ready: true, blocked_reasons: [],
    } } as never)

    await expect(podcastsApi.getPodcastReadiness([{
      kind: 'notebook', notebookId: 'notebook:research',
    }])).resolves.toEqual(expect.objectContaining({
      preview: expect.objectContaining({ selectionFingerprint: 'a'.repeat(64) }),
      stagePlans: [expect.objectContaining({ modelId: 'local-outline' })],
    }))
  })

  it('sends a confirmed Studio submission without source text or filesystem paths', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: {
      job_id: 'command:podcast-one', status: 'submitted', message: 'accepted',
      episode_profile: 'Local Episode', episode_name: 'Research synthesis', mode: 'deep_dive',
    } } as never)

    await expect(podcastsApi.submitStudioPodcast({
      selections: [{ kind: 'notebook', notebookId: 'notebook:research' }],
      selectionFingerprint: 'a'.repeat(64),
      idempotencyKey: 'podcast-submit-ui-1',
      episodeProfile: 'Local Episode', speakerProfile: 'Local Voice',
      episodeName: 'Research synthesis',
      editorialBrief: {
        centralQuestion: 'What should change after this research?',
        audience: 'Research team',
        outline: ['Context', 'Decision'],
      },
    })).resolves.toMatchObject({ jobId: 'command:podcast-one' })

    expect(apiClient.post).toHaveBeenCalledWith('/podcasts/studio/submit', expect.objectContaining({
      selections: [{ kind: 'notebook', notebook_id: 'notebook:research' }],
      selection_fingerprint: 'a'.repeat(64), confirmed: true,
      editorial_brief: {
        central_question: 'What should change after this research?',
        audience: 'Research team',
        purpose: null,
        format: null,
        target_minutes: null,
        required_takeaway: null,
        include_unanswered_questions: null,
        evidence_policy: null,
        episode_profile_name: null,
        speaker_profile_name: null,
        outline: ['Context', 'Decision'],
      },
      production_overrides: {},
    }))
    expect(JSON.stringify(vi.mocked(apiClient.post).mock.calls[0][1])).not.toContain('/Users/')
  })

  it('sends every editorial field and production overrides through the wire contract', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: {
      job_id: 'command:podcast-full', status: 'submitted', message: 'accepted',
      episode_profile: 'Local Episode', episode_name: 'Research synthesis', mode: 'critique',
    } } as never)

    await podcastsApi.submitStudioPodcast({
      selections: [{ kind: 'notebook', notebookId: 'notebook:research' }],
      selectionFingerprint: 'a'.repeat(64), idempotencyKey: 'podcast-full-ui-1',
      episodeProfile: 'Local Episode', speakerProfile: 'Local Voice', episodeName: 'Research synthesis',
      mode: 'critique', productionOverrides: {
        podcast_outline: 'outline-alt', podcast_script: 'script-alt',
        text_to_speech: 'voice-alt', speech_to_text: 'stt-alt',
      },
      editorialBrief: {
        centralQuestion: 'What changed?', audience: 'expert', purpose: 'analyze', format: 'critique',
        targetMinutes: 42, requiredTakeaway: 'Use the threshold.', includeUnansweredQuestions: true,
        evidencePolicy: 'interpretation', episodeProfileName: 'Local Episode', speakerProfileName: 'Local Voice',
        outline: ['Context', 'Decision'],
      },
    })

    expect(apiClient.post).toHaveBeenCalledWith('/podcasts/studio/submit', expect.objectContaining({
      production_overrides: {
        podcast_outline: 'outline-alt', podcast_script: 'script-alt',
        text_to_speech: 'voice-alt', speech_to_text: 'stt-alt',
      },
      editorial_brief: {
        central_question: 'What changed?', audience: 'expert', purpose: 'analyze', format: 'critique',
        target_minutes: 42, required_takeaway: 'Use the threshold.', include_unanswered_questions: true,
        evidence_policy: 'interpretation', episode_profile_name: 'Local Episode', speaker_profile_name: 'Local Voice',
        outline: ['Context', 'Decision'],
      },
    }))
  })
})

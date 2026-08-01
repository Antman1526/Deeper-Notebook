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
})

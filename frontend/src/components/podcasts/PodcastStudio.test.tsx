import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api/podcasts', () => ({
  podcastsApi: {
    getPodcastReadiness: vi.fn(),
    listEpisodeProfiles: vi.fn(),
    listSpeakerProfiles: vi.fn(),
    submitStudioPodcast: vi.fn(),
  },
}))

import { podcastsApi } from '@/lib/api/podcasts'
import { PodcastStudio } from './PodcastStudio'

describe('PodcastStudio', () => {
  beforeEach(() => vi.resetAllMocks())

  it('keeps an editable editorial brief local until a later confirmation', () => {
    render(<PodcastStudio seedDocumentIds={['knowledge_engine_document:plan']} />)

    fireEvent.change(screen.getByLabelText('Central question'), {
      target: { value: 'What changes after the research is connected?' },
    })
    fireEvent.change(screen.getByLabelText('Audience'), { target: { value: 'expert' } })

    expect(screen.getByLabelText('Central question')).toHaveValue('What changes after the research is connected?')
    expect(screen.getByLabelText('Audience')).toHaveValue('expert')
    expect(screen.getByText('Opening the Studio does not submit a production job.')).toBeVisible()
  })

  it('moves outline segments with explicit keyboard-accessible controls', () => {
    render(<PodcastStudio seedDocumentIds={['knowledge_engine_document:plan']} />)

    fireEvent.click(screen.getByRole('button', { name: 'Move Findings earlier' }))

    expect(screen.getByRole('status')).toHaveTextContent('Findings moved to position 1')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Move Findings earlier' }))
  })

  it('checks readiness only after explicit review and submits the editorial brief after confirmation', async () => {
    vi.mocked(podcastsApi.getPodcastReadiness).mockResolvedValue({
      preview: {
        selectionFingerprint: 'a'.repeat(64), entries: [{
          stableId: 'knowledge_engine_document:plan', title: 'Research plan', authorityKind: 'app_owned',
          relativeLocator: null, revisionId: null, fingerprint: 'b'.repeat(64),
          state: 'included', reason: 'included', estimatedCharacters: 120,
        }], includedCharacters: 120, requiresBatchEngine: false,
        currentWorkerEligible: true, blockedReasons: [],
      }, stagePlans: [], ready: true, blockedReasons: [],
    })
    vi.mocked(podcastsApi.listEpisodeProfiles).mockResolvedValue([{
      id: 'episode_profile:local', name: 'Local Episode', description: '', speaker_config: 'Local Voice',
      default_briefing: '', num_segments: 4,
    }])
    vi.mocked(podcastsApi.listSpeakerProfiles).mockResolvedValue([{
      id: 'speaker_profile:local', name: 'Local Voice', description: '', speakers: [],
    }])
    vi.mocked(podcastsApi.submitStudioPodcast).mockResolvedValue({
      jobId: 'command:podcast-one', status: 'submitted', message: 'accepted',
      episodeProfile: 'Local Episode', episodeName: 'Research plan', mode: 'deep_dive',
    })

    render(<PodcastStudio seedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(podcastsApi.getPodcastReadiness).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Central question'), {
      target: { value: 'What should change after the research?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Prepare production review' }))

    expect(await screen.findByText('Production profiles')).toBeVisible()
    expect(podcastsApi.getPodcastReadiness).toHaveBeenCalledWith([
      { kind: 'knowledge_document', documentId: 'knowledge_engine_document:plan' },
    ])
    fireEvent.click(screen.getByRole('button', { name: 'Continue to confirmation' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm production' }))

    await waitFor(() => expect(podcastsApi.submitStudioPodcast).toHaveBeenCalledWith(expect.objectContaining({
      selections: [{ kind: 'knowledge_document', documentId: 'knowledge_engine_document:plan' }],
      editorialBrief: {
        centralQuestion: 'What should change after the research?',
        audience: 'practitioner',
        outline: ['Introduction', 'Findings', 'Takeaway'],
      },
      reviewOutline: true,
    })))
  })
})

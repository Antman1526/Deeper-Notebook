import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useRetryPodcastEpisode } from './use-podcasts'

const { retryEpisode, push, openStudio, toast } = vi.hoisted(() => ({
  retryEpisode: vi.fn(),
  push: vi.fn(),
  openStudio: vi.fn(),
  toast: vi.fn(),
}))

vi.mock('@/lib/api/podcasts', () => ({
  podcastsApi: { retryEpisode },
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/lib/stores/podcast-studio-store', () => ({
  usePodcastStudioStore: (selector: (state: { open: typeof openStudio }) => unknown) =>
    selector({ open: openStudio }),
}))

vi.mock('@/lib/hooks/use-toast', () => ({
  useToast: () => ({ toast }),
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
}

describe('useRetryPodcastEpisode', () => {
  beforeEach(() => {
    retryEpisode.mockReset()
    push.mockReset()
    openStudio.mockReset()
    toast.mockReset()
  })

  it('opens Studio and navigates without a false retry-started toast', async () => {
    retryEpisode.mockResolvedValue({
      status: 'preview_required',
      code: 'podcast_selection_changed',
      message: 'Review the changed selection.',
      episodeId: 'episode:changed',
      selections: [{
        kind: 'knowledge_document',
        documentId: 'knowledge_engine_document:research',
        expectedRevisionId: null,
      }],
      selectionFingerprint: 'a'.repeat(64),
      preview: null,
    })

    const { result } = renderHook(() => useRetryPodcastEpisode(), { wrapper })
    await act(async () => {
      await result.current.mutateAsync('episode:changed')
    })

    expect(openStudio).toHaveBeenCalledWith([{
      kind: 'knowledge_document',
      documentId: 'knowledge_engine_document:research',
      expectedRevisionId: null,
    }], 'studio')
    expect(push).toHaveBeenCalledWith('/podcasts/studio')
    expect(toast).not.toHaveBeenCalledWith(expect.objectContaining({
      title: 'podcasts.retryStarted',
    }))
  })

  it('fails closed with empty tampered-safe references without submitting', async () => {
    retryEpisode.mockResolvedValue({
      status: 'preview_required',
      code: 'podcast_selection_tampered',
      message: 'Review fresh references.',
      episodeId: 'episode:tampered',
      selections: [],
      selectionFingerprint: null,
      preview: null,
    })

    const { result } = renderHook(() => useRetryPodcastEpisode(), { wrapper })
    await act(async () => {
      await result.current.mutateAsync('episode:tampered')
    })

    expect(openStudio).toHaveBeenCalledWith([], 'studio')
    expect(push).toHaveBeenCalledWith('/podcasts/studio')
    expect(toast).not.toHaveBeenCalledWith(expect.objectContaining({
      title: 'podcasts.retryStarted',
    }))
  })

  it('keeps the submitted retry toast for normal retries', async () => {
    retryEpisode.mockResolvedValue({
      status: 'submitted',
      jobId: 'command:retry',
      message: 'Retry submitted successfully',
    })

    const { result } = renderHook(() => useRetryPodcastEpisode(), { wrapper })
    await act(async () => {
      await result.current.mutateAsync('episode:normal')
    })

    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'podcasts.retryStarted' }))
    expect(push).not.toHaveBeenCalled()
  })
})

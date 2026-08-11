import { beforeEach, describe, expect, it, vi } from 'vitest'

import apiClient from './client'
import { evaluationsApi } from './evaluations'

vi.mock('./client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

describe('evaluationsApi notebook-scoped lookup', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('treats a 404 latest lookup as an empty evaluation without a toast path', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce({ response: { status: 404 } })

    await expect(
      evaluationsApi.latest('notebook:one', { messageId: 'message:one' }),
    ).resolves.toBeNull()
    expect(apiClient.get).toHaveBeenCalledWith(
      '/evaluations/latest',
      expect.objectContaining({
        headers: { 'x-skip-error-toast': '1' },
        params: { notebook_id: 'notebook:one', message_id: 'message:one' },
      }),
    )
  })

  it('uses one bounded batch request and deduplicates message IDs', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: {} })

    await expect(
      evaluationsApi.latestBatch('notebook:one', [
        'message:one',
        'message:one',
        'message:two',
      ]),
    ).resolves.toEqual({})
    expect(apiClient.post).toHaveBeenCalledTimes(1)
    expect(apiClient.post).toHaveBeenCalledWith(
      '/evaluations/latest/batch',
      { notebook_id: 'notebook:one', message_ids: ['message:one', 'message:two'] },
      { headers: { 'x-skip-error-toast': '1' } },
    )
  })

  it('rejects more than 100 unique message IDs before making a request', async () => {
    await expect(
      evaluationsApi.latestBatch(
        'notebook:one',
        Array.from({ length: 101 }, (_, index) => `message:${index}`),
      ),
    ).rejects.toThrow(/100/iu)
    expect(apiClient.post).not.toHaveBeenCalled()
  })
})

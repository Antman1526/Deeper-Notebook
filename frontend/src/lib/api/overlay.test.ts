import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

import apiClient from './client'
import { overlayApi } from './overlay'

const mockGet = vi.mocked(apiClient.get)
const mockPut = vi.mocked(apiClient.put)

const validOverlayPage = {
  overlay: {
    id: 'overlay_note:one',
    source_authority: 'overlay',
    space_id: 'overlay_space:default',
    projected_note_id: 'note:overlay-one',
    stable_id: 'a'.repeat(20),
    kind: 'daily',
    date_key: '2026-07-29',
    relative_path: 'Daily/2026-07-29.md',
    title: 'Today',
    content_hash: 'a'.repeat(64),
    revision: 1,
    projection_state: 'current',
    encoding: 'utf-8',
    newline: 'lf',
    created_at: '2026-07-29T12:00:00+00:00',
    updated_at: '2026-07-29T12:00:00+00:00',
  },
  note: { id: 'note:overlay-one', title: 'Today', markdown: '# Today\n' },
  blocks: [],
  tasks: [],
  outgoing_links: [],
  backlinks: [],
  graph: null,
} as const

describe('overlay API boundary', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('rejects absolute paths, invalid hashes, authority substitution, and unrelated note identity', async () => {
    for (const overlay of [
      { ...validOverlayPage.overlay, relative_path: '/Users/owner/private.md' },
      { ...validOverlayPage.overlay, content_hash: 'bad' },
      { ...validOverlayPage.overlay, source_authority: 'external-vault' },
    ]) {
      mockGet.mockResolvedValueOnce({ data: { ...validOverlayPage, overlay } } as never)
      await expect(overlayApi.page('overlay_note:one')).rejects.toThrow()
    }

    mockGet.mockResolvedValueOnce({
      data: { ...validOverlayPage, note: { ...validOverlayPage.note, id: 'note:external' } },
    } as never)
    await expect(overlayApi.page('overlay_note:one')).rejects.toThrow()
  })

  it('rejects unexpected wire fields', async () => {
    mockGet.mockResolvedValue({
      data: { ...validOverlayPage, overlay: { ...validOverlayPage.overlay, vault_id: 'vault:forbidden' } },
    } as never)

    await expect(overlayApi.page('overlay_note:one')).rejects.toThrow()
  })

  it('encodes IDs and serializes only the strict update contract', async () => {
    mockPut.mockResolvedValue({
      data: {
        ...validOverlayPage,
        overlay: { ...validOverlayPage.overlay, id: 'overlay_note:a/b' },
      },
    } as never)

    await overlayApi.update('overlay_note:a/b', {
      title: 'Today',
      markdown: '# Today\n',
      expectedRevision: 1,
      idempotencyKey: 'save-1',
      ignored: 'not-on-the-wire',
    } as never)

    expect(mockPut).toHaveBeenCalledWith(
      '/deeper-notebook/overlay/notes/overlay_note%3Aa%2Fb',
      {
        title: 'Today',
        markdown: '# Today\n',
        expected_revision: 1,
        idempotency_key: 'save-1',
      },
    )
  })
})

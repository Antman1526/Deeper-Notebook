import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

import apiClient from './client'
import { overlayApi } from './overlay'

const mockGet = vi.mocked(apiClient.get)
const mockPut = vi.mocked(apiClient.put)

const validOverlayLink = {
  id: 'note_link:one',
  source_note_id: 'note:overlay-one',
  source_overlay_note_id: 'overlay_note:one',
  source_relative_path: 'Daily/2026-07-29.md',
  target_note_id: 'note:overlay-two',
  target_overlay_note_id: 'overlay_note:two',
  target_note_title: 'Two',
  target_relative_path: 'Notes/20260729-1542 Two.md',
  target_text: 'Two',
  link_kind: 'wikilink',
  resolved: true,
  source_start: 0,
  source_end: 5,
} as const

const validOverlayGraph = {
  nodes: [
    { id: 'note:overlay-one', title: 'Today', source_format: 'markdown' },
    { id: 'note:overlay-two', title: 'Two', source_format: 'markdown' },
  ],
  edges: [{
    id: 'note_link:one',
    source: 'note:overlay-one',
    target: 'note:overlay-two',
    kind: 'wikilink',
    resolved: true,
  }],
} as const

const validOverlayPage = {
  knowledge_document_id: null,
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
  editable_markdown: '# Today\n',
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

    const missingEditableBody = { ...validOverlayPage }
    delete (missingEditableBody as { editable_markdown?: string }).editable_markdown
    mockGet.mockResolvedValueOnce({ data: missingEditableBody } as never)
    await expect(overlayApi.page('overlay_note:one')).rejects.toThrow()
  })

  it('requires explicit nullable overlay identity mappings on every overlay link', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        ...validOverlayPage,
        outgoing_links: [validOverlayLink],
        graph: validOverlayGraph,
      },
    } as never)
    await expect(overlayApi.page('overlay_note:one')).resolves.toMatchObject({
      outgoing_links: [{
        source_note_id: 'note:overlay-one',
        source_overlay_note_id: 'overlay_note:one',
        source_relative_path: 'Daily/2026-07-29.md',
        target_note_id: 'note:overlay-two',
        target_overlay_note_id: 'overlay_note:two',
      }],
      graph: {
        nodes: [
          { id: 'note:overlay-one' },
          { id: 'note:overlay-two' },
        ],
        edges: [{
          source: 'note:overlay-one',
          target: 'note:overlay-two',
        }],
      },
    })

    for (const missingField of [
      'source_overlay_note_id',
      'source_relative_path',
      'target_overlay_note_id',
    ] as const) {
      const link: Partial<typeof validOverlayLink> = { ...validOverlayLink }
      delete link[missingField]
      mockGet.mockResolvedValueOnce({
        data: {
          ...validOverlayPage,
          outgoing_links: [link],
        },
      } as never)
      await expect(overlayApi.page('overlay_note:one')).rejects.toThrow()
    }

    mockGet.mockResolvedValueOnce({
      data: {
        ...validOverlayPage,
        outgoing_links: [{
          ...validOverlayLink,
          target_overlay_note_id: null,
        }],
        backlinks: [{
          ...validOverlayLink,
          source_note_id: 'note:external',
          source_overlay_note_id: null,
          source_relative_path: null,
          target_note_id: 'note:overlay-one',
          target_overlay_note_id: 'overlay_note:one',
          target_note_title: 'Today',
          target_relative_path: 'Daily/2026-07-29.md',
        }],
      },
    } as never)
    await expect(overlayApi.page('overlay_note:one')).resolves.toMatchObject({
      outgoing_links: [{ target_overlay_note_id: null }],
      backlinks: [{
        source_overlay_note_id: null,
        source_relative_path: null,
      }],
    })
  })

  it('accepts optional strict unified identity IDs', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        ...validOverlayPage,
        knowledge_document_id: 'knowledge_engine_document:current',
        blocks: [{ knowledge_block_id: 'knowledge_engine_block:heading' }],
      },
    } as never)
    await expect(overlayApi.page('overlay_note:one')).resolves.toMatchObject({
      knowledge_document_id: 'knowledge_engine_document:current',
      blocks: [{ knowledge_block_id: 'knowledge_engine_block:heading' }],
    })
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

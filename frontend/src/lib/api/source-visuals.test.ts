import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiPost = vi.fn()
const apiDelete = vi.fn()
const apiGet = vi.fn()

vi.mock('@/lib/api/client', () => ({
  default: {
    post: (...args: unknown[]) => apiPost(...args),
    delete: (...args: unknown[]) => apiDelete(...args),
    get: (...args: unknown[]) => apiGet(...args),
  },
}))

import { sourceVisualsApi } from './source-visuals'
import { searchApi } from './search'
import { captureApi } from './capture'
import {
  decodeSourceVisual,
  decodeSourceVisualStatus,
  decodeSourceWithVisual,
} from '@/lib/types/source-visuals'

const HASH = 'a'.repeat(64)
const TOKEN = 'b'.repeat(64)

const VISUAL = {
  source_id: 'source:one',
  content_sha256: HASH,
  asset_sha256: TOKEN,
  origin: 'embedded',
  source_locator: { page: 2 },
  alt_text: 'A chart comparing the evidence.',
  width: 1280,
  height: 720,
  mime_type: 'image/webp',
  asset_url: `/api/sources/source%3Aone/visual?v=${HASH}`,
  created_at: '2026-08-15T12:00:00Z',
  updated_at: '2026-08-15T12:00:00Z',
} as const

const SOURCE = {
  id: 'source:one',
  title: 'Evidence',
  topics: [],
  provenance: {},
  source_type: 'upload',
  notebook_count: 1,
  is_shared: false,
  asset: null,
  embedded: true,
  embedded_chunks: 2,
  insights_count: 1,
  summary_preview: null,
  created: '2026-08-15T12:00:00Z',
  updated: '2026-08-15T12:00:00Z',
  file_available: true,
  extracted_char_count: 100,
  extraction_quality: 'ok',
  command_id: null,
  status: null,
  processing_info: null,
} as const

describe('source visual decoders', () => {
  it.each([
    ['embedded page', { origin: 'embedded', source_locator: { page: 1 } }],
    ['embedded resource', { origin: 'embedded', source_locator: { resource_id: 'image-1' } }],
    ['video frame', { origin: 'video_frame', source_locator: { timestamp_ms: 0 } }],
    ['audio artwork', { origin: 'audio_artwork', source_locator: { resource_id: 'cover' } }],
  ])('accepts %s receipts', (_label, pairing) => {
    expect(decodeSourceVisual({ ...VISUAL, ...pairing })).toMatchObject(pairing)
  })

  it.each(['queued', 'processing', 'unavailable', 'failed'])('accepts %s status', (state) => {
    expect(decodeSourceVisualStatus({
      state,
      command_id: null,
      error_code: state === 'failed' ? 'extractor.failed' : null,
      updated_at: '2026-08-15T12:00:00Z',
    }).state).toBe(state)
  })

  it.each([
    ['unknown origin', { origin: 'generated' }],
    ['extra key', { private_path: '/tmp/private.webp' }],
    ['uppercase hash', { asset_sha256: 'A'.repeat(64) }],
    ['short hash', { content_sha256: 'abc' }],
    ['zero width', { width: 0 }],
    ['oversized width', { width: 1281 }],
    ['oversized height', { height: 721 }],
    ['wrong mime', { mime_type: 'image/svg+xml' }],
    ['empty alt', { alt_text: '' }],
    ['oversized alt', { alt_text: 'a'.repeat(301) }],
    ['external URL', { asset_url: `https://example.com/a.webp?v=${HASH}` }],
    ['absolute URL', { asset_url: `/private/tmp/a.webp?v=${HASH}` }],
    ['path-bearing URL', { asset_url: `/api/sources/source%3Aone/visual/secret?v=${HASH}` }],
    ['cross-source URL', { asset_url: `/api/sources/source%3Atwo/visual?v=${HASH}` }],
    ['invalid page', { source_locator: { page: 0 } }],
    ['oversized page', { source_locator: { page: 25 } }],
    ['invalid timestamp', { origin: 'video_frame', source_locator: { timestamp_ms: -1 } }],
    ['empty resource', { source_locator: { resource_id: '' } }],
    ['oversized resource', { source_locator: { resource_id: 'a'.repeat(129) } }],
    ['multiple locators', { source_locator: { page: 1, resource_id: 'image-1' } }],
    ['wrong pairing', { origin: 'audio_artwork', source_locator: { page: 1 } }],
  ])('rejects %s', (_label, patch) => {
    expect(() => decodeSourceVisual({ ...VISUAL, ...patch })).toThrow()
  })

  it('rejects unknown statuses, unknown keys, and raw error text', () => {
    expect(() => decodeSourceVisualStatus({ state: 'ready', command_id: null, error_code: null, updated_at: '2026-08-15T12:00:00Z' })).toThrow()
    expect(() => decodeSourceVisualStatus({ state: 'failed', command_id: null, error_code: null, updated_at: '2026-08-15T12:00:00Z', detail: 'private stack' })).toThrow()
    expect(() => decodeSourceVisualStatus({ state: 'failed', command_id: null, error_code: 'Raw exception: /tmp/a', updated_at: '2026-08-15T12:00:00Z' })).toThrow()
  })

  it('drops an invalid visual and status without dropping its strict source', () => {
    const decoded = decodeSourceWithVisual({
      ...SOURCE,
      visual: { ...VISUAL, mime_type: 'image/svg+xml' },
      visual_status: { state: 'unknown', updated_at: '2026-08-15T12:00:00Z' },
    })
    expect(decoded.id).toBe('source:one')
    expect(decoded.visual).toBeNull()
    expect(decoded.visual_status).toBeNull()
    expect(() => decodeSourceWithVisual({ ...SOURCE, unexpected: true })).toThrow()
  })

  it('drops a valid receipt belonging to a different containing source', () => {
    const decoded = decodeSourceWithVisual({
      ...SOURCE,
      visual: {
        ...VISUAL,
        source_id: 'source:two',
        asset_url: `/api/sources/source%3Atwo/visual?v=${HASH}`,
      },
      visual_status: null,
    })
    expect(decoded.visual).toBeNull()
  })
})

describe('sourceVisualsApi', () => {
  beforeEach(() => vi.clearAllMocks())

  it('encodes source IDs and sends the caller-owned request id', async () => {
    apiPost.mockResolvedValue({ data: { source_id: 'source:one', command_id: 'command:one', content_sha256: HASH, asset_sha256: null, origin: null, width: null, height: null, duration_ms: null, outcome: 'queued', error_code: null } })
    await sourceVisualsApi.refresh('source:folder/one', 'request-one')
    expect(apiPost).toHaveBeenCalledWith('/sources/source%3Afolder%2Fone/visual:refresh', { request_id: 'request-one' })
  })

  it('sends a body with DELETE and rejects unknown response keys', async () => {
    apiDelete.mockResolvedValue({ data: { source_id: 'source:one', command_id: null, content_sha256: HASH, asset_sha256: null, origin: null, width: null, height: null, duration_ms: null, outcome: 'deleted', error_code: null } })
    await sourceVisualsApi.remove('source:one', 'request-two')
    expect(apiDelete).toHaveBeenCalledWith('/sources/source%3Aone/visual', { data: { request_id: 'request-two' } })

    apiDelete.mockResolvedValue({ data: { source_id: 'source:one', command_id: null, content_sha256: HASH, asset_sha256: null, origin: null, width: null, height: null, duration_ms: null, outcome: 'deleted', error_code: null, detail: '/tmp/private' } })
    await expect(sourceVisualsApi.remove('source:one', 'request-three')).rejects.toThrow()
  })
})

describe('source-bearing API boundaries', () => {
  beforeEach(() => vi.clearAllMocks())

  it('fails soft for malformed search visuals without dropping the search result', async () => {
    apiPost.mockResolvedValue({
      data: {
        results: [{ id: 'source:one', title: 'Evidence', parent_id: '', final_score: 1, created: 'now', updated: 'now', visual: { ...VISUAL, mime_type: 'image/svg+xml' } }],
        total_count: 1,
        search_type: 'text',
      },
    })
    const response = await searchApi.search({ query: 'evidence', type: 'text', limit: 10, search_sources: true, search_notes: false, minimum_score: 0 })
    expect(response.results[0]).toEqual(expect.objectContaining({ id: 'source:one', visual: null }))
  })

  it('strictly decodes search envelopes and binds direct and insight receipts to their source', async () => {
    const otherVisual = { ...VISUAL, source_id: 'source:two', asset_url: `/api/sources/source%3Atwo/visual?v=${HASH}` }
    apiPost.mockResolvedValueOnce({
      data: {
        results: [
          { id: 'source:one', title: 'One', parent_id: 'source:one', relevance: 1, visual: otherVisual, visual_status: null },
          { id: 'source_insight:one', title: 'Insight', parent_id: 'source:one', relevance: 0.9, visual: otherVisual, visual_status: null },
        ],
        total_count: 2,
        search_type: 'text',
      },
    })
    const response = await searchApi.search({ query: 'evidence', type: 'text', limit: 10, search_sources: true, search_notes: false, minimum_score: 0 })
    expect(response.results.map(result => result.visual)).toEqual([null, null])

    apiPost.mockResolvedValueOnce({ data: { results: [], total_count: 0, search_type: 'text', debug_path: '/tmp/a' } })
    await expect(searchApi.search({ query: 'evidence', type: 'text', limit: 10, search_sources: true, search_notes: false, minimum_score: 0 })).rejects.toThrow()
  })

  it('preserves the established one-thousand-result search response bound', async () => {
    apiPost.mockResolvedValueOnce({
      data: {
        results: Array.from({ length: 201 }, (_, index) => ({ id: `note:${index}`, title: `Note ${index}` })),
        total_count: 201,
        search_type: 'text',
      },
    })
    const response = await searchApi.search({ query: 'note', type: 'text', limit: 1000, search_sources: false, search_notes: true, minimum_score: 0 })
    expect(response.results).toHaveLength(201)
  })

  it('strictly decodes capture-linked source wrappers and fails soft for their visual', async () => {
    apiGet.mockResolvedValue({ data: [{ id: 'capture:one', root_path: '/approved', relative_path: 'one.pdf', filename: 'one.pdf', extension: '.pdf', state: 'ready', sha256: HASH, byte_size: 1, modified_ns: 1, reason: null, linked_source: { id: 'source:one', visual: { ...VISUAL, width: 0 } } }] })
    const items = await captureApi.items()
    expect(items[0].linked_source).toEqual({ id: 'source:one', visual: null })

    apiGet.mockResolvedValue({ data: [{ id: 'capture:one', root_path: '/approved', relative_path: 'one.pdf', filename: 'one.pdf', extension: '.pdf', state: 'ready', sha256: HASH, byte_size: 1, modified_ns: 1, reason: null, linked_source: { id: 'source:one', visual: VISUAL, private_path: '/tmp/a' } }] })
    await expect(captureApi.items()).rejects.toThrow()
  })

  it('binds capture receipts to the linked source and rejects unknown capture item keys', async () => {
    const otherVisual = { ...VISUAL, source_id: 'source:two', asset_url: `/api/sources/source%3Atwo/visual?v=${HASH}` }
    const baseItem = { id: 'capture:one', root_path: '/approved', relative_path: 'one.pdf', filename: 'one.pdf', extension: '.pdf', state: 'ready', sha256: HASH, byte_size: 1, modified_ns: 1, reason: null }
    apiGet.mockResolvedValueOnce({ data: [{ ...baseItem, linked_source: { id: 'source:one', visual: otherVisual } }] })
    expect((await captureApi.items())[0].linked_source?.visual).toBeNull()

    apiGet.mockResolvedValueOnce({ data: [{ ...baseItem, linked_source: null, worker_error: 'private' }] })
    await expect(captureApi.items()).rejects.toThrow()

    apiPost.mockResolvedValueOnce({ data: { items: [], debug: true } })
    await expect(captureApi.scan()).rejects.toThrow()
  })
})

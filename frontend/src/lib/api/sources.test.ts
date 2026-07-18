import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiPost = vi.fn()

vi.mock('@/lib/api/client', () => ({
  default: {
    post: (...args: unknown[]) => apiPost(...args),
  },
}))

import { sourcesApi } from './sources'

function sourceResponse() {
  return {
    id: 'source:1',
    title: 'paper.pdf',
    asset: null,
    full_text: '',
    embedded: false,
    embedded_chunks: 0,
    insights_count: 0,
    created: '2026-06-23T00:00:00Z',
    updated: '2026-06-23T00:00:00Z',
  }
}

describe('sourcesApi source creation helpers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses the multi-notebook upload contract and keeps embedding enabled', async () => {
    apiPost.mockResolvedValue({
      data: sourceResponse(),
    })

    const file = new File(['test'], 'paper.pdf', { type: 'application/pdf' })

    await sourcesApi.upload(file, 'notebook:alpha')

    expect(apiPost).toHaveBeenCalledOnce()
    const [path, body, config] = apiPost.mock.calls[0]
    expect(path).toBe('/sources')
    expect(config).toEqual({
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })

    const formData = body as FormData
    expect(formData.get('file')).toBe(file)
    expect(formData.get('notebooks')).toBe(JSON.stringify(['notebook:alpha']))
    expect(formData.get('notebook_id')).toBe('notebook:alpha')
    expect(formData.get('type')).toBe('upload')
    expect(formData.get('embed')).toBe('true')
    expect(formData.get('delete_source')).toBe('false')
    expect(formData.get('async_processing')).toBe('true')
  })

  it('defaults general source creation to searchable queued processing', async () => {
    apiPost.mockResolvedValue({ data: sourceResponse() })

    await sourcesApi.create({
      type: 'link',
      url: 'https://example.com/research',
      notebooks: ['notebook:alpha'],
    })

    expect(apiPost).toHaveBeenCalledOnce()
    const [path, body] = apiPost.mock.calls[0]
    expect(path).toBe('/sources')
    const formData = body as FormData
    expect(formData.get('type')).toBe('link')
    expect(formData.get('url')).toBe('https://example.com/research')
    expect(formData.get('notebooks')).toBe(JSON.stringify(['notebook:alpha']))
    expect(formData.get('embed')).toBe('true')
    expect(formData.get('async_processing')).toBe('true')
  })

  it('keeps explicit embed=false and async_processing=false for ingest-only source creation', async () => {
    apiPost.mockResolvedValue({ data: sourceResponse() })

    await sourcesApi.create({
      type: 'text',
      title: 'Archive only',
      content: 'Do not embed this note',
      notebooks: ['notebook:alpha'],
      embed: false,
      async_processing: false,
    })

    const [, body] = apiPost.mock.calls[0]
    const formData = body as FormData
    expect(formData.get('embed')).toBe('false')
    expect(formData.get('async_processing')).toBe('false')
  })
})

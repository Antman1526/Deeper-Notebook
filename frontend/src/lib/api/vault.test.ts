import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

import apiClient from './client'
import { vaultApi, vaultFileSchema } from './vault'

const mockedGet = vi.mocked(apiClient.get)

const fileFixture = {
  id: 'vault_file:one',
  vault_id: 'vault:one',
  relative_path: 'pages/one.md',
  note_id: 'note:one',
  file_kind: 'markdown',
  format: 'obsidian',
  content_hash: 'a'.repeat(64),
  parse_status: 'parsed',
  size_bytes: 123,
  modified_ns: 456,
  encoding: 'utf-8',
  newline: 'lf',
  deleted_state: 'present',
}

const linkFixture = {
  id: 'vault_link:one',
  source_note_id: 'note:one',
  target_note_id: null,
  target_text: 'Two',
  link_kind: 'wikilink',
  resolved: false,
  source_start: 0,
  source_end: 7,
}

function pageFixture(overrides: Record<string, unknown> = {}) {
  return {
    file: fileFixture,
    note: { id: 'note:one', title: 'One', markdown: '# One' },
    blocks: [],
    tasks: [],
    outgoing_links: [],
    backlinks: [],
    ...overrides,
  }
}

describe('vault API boundary', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('validates a vault file before exposing it to callers', () => {
    expect(vaultFileSchema.parse(fileFixture)).toMatchObject(fileFixture)
    expect(() => vaultFileSchema.parse({ ...fileFixture, note_id: undefined })).toThrow()
    expect(() => vaultFileSchema.parse({ ...fileFixture, parse_status: 'unknown' })).toThrow()
  })

  it.each([
    '/Users/owner/secret.md',
    'C:\\Users\\owner\\secret.md',
    '\\\\server\\share\\secret.md',
    '//server/share/secret.md',
  ])('rejects POSIX, drive, and UNC absolute paths from file responses: %s', async (relative_path) => {
    mockedGet.mockResolvedValue({ data: [{ ...fileFixture, relative_path }] } as never)
    await expect(vaultApi.files('vault:one')).rejects.toThrow(/absolute path/i)
  })

  it('rejects absolute paths from page and graph responses', async () => {
    mockedGet
      .mockResolvedValueOnce({
        data: pageFixture({
          note: {
            id: 'note:one',
            source_path: '/Users/owner/secret.md',
          },
        }),
      } as never)
      .mockResolvedValueOnce({ data: { nodes: [{ id: '/Users/owner/secret.md', title: 'Secret', source_format: 'obsidian' }], edges: [] } } as never)

    await expect(vaultApi.page('vault:one', 'note:one'))
      .rejects.toMatchObject({ code: 'page-invalid' })
    await expect(vaultApi.graph('vault:one', 'note:one')).rejects.toThrow(/absolute path/i)
  })

  it('accepts a page with canonical requested identity', async () => {
    mockedGet.mockResolvedValueOnce({ data: pageFixture() } as never)

    await expect(vaultApi.page('vault:one', 'note:one'))
      .resolves.toMatchObject({
        file: fileFixture,
        note: { id: 'note:one' },
      })
  })

  it.each([
    ['file vault', { file: { ...fileFixture, vault_id: 'vault:other' } }],
    ['file note', { file: { ...fileFixture, note_id: 'note:other' } }],
    ['page note', { note: { id: 'note:other', title: 'Other' } }],
  ])('rejects a page whose %s conflicts with requested identity', async (_field, overrides) => {
    mockedGet.mockResolvedValueOnce({ data: pageFixture(overrides) } as never)

    await expect(vaultApi.page('vault:one', 'note:one'))
      .rejects.toMatchObject({ code: 'page-invalid' })
  })

  it.each([
    '',
    '/Users/owner/private/two.md',
    '../outside.md',
    'pages\\two.md',
    'pages//two.md',
    'pages/./two.md',
    'pages/\0two.md',
    'C:/private/two.md',
    ' pages/two.md',
    'pages/two.md ',
  ])('rejects noncanonical target path %j', async (targetRelativePath) => {
    mockedGet.mockResolvedValueOnce({
      data: pageFixture({
        outgoing_links: [{
          ...linkFixture,
          resolved: true,
          target_note_id: 'note:two',
          target_note_title: 'Two',
          target_relative_path: targetRelativePath,
        }],
      }),
    } as never)

    await expect(vaultApi.page('vault:one', 'note:one'))
      .rejects.toMatchObject({ code: 'page-invalid' })
  })

  it('classifies missing canonical file metadata separately', async () => {
    mockedGet.mockResolvedValueOnce({
      data: pageFixture({ file: undefined }),
    } as never)

    await expect(vaultApi.page('vault:one', 'note:one'))
      .rejects.toMatchObject({ code: 'canonical-path-unavailable' })
  })

  it('classifies a noncanonical page file path separately', async () => {
    mockedGet.mockResolvedValueOnce({
      data: pageFixture({
        file: { ...fileFixture, relative_path: '../outside.md' },
      }),
    } as never)

    await expect(vaultApi.page('vault:one', 'note:one'))
      .rejects.toMatchObject({ code: 'canonical-path-unavailable' })
  })

  it.each([null, 'short', 'g'.repeat(64)])(
    'rejects page content hash %j',
    async (contentHash) => {
      mockedGet.mockResolvedValueOnce({
        data: pageFixture({
          file: { ...fileFixture, content_hash: contentHash },
        }),
      } as never)

      await expect(vaultApi.page('vault:one', 'note:one'))
        .rejects.toMatchObject({ code: 'page-invalid' })
    },
  )

  it.each([
    ['target note ID', { target_note_id: null }],
    ['target note title', { target_note_title: null }],
    ['target relative path', { target_relative_path: null }],
  ])('rejects a resolved link missing canonical %s', async (_field, linkOverrides) => {
    mockedGet.mockResolvedValueOnce({
      data: pageFixture({
        outgoing_links: [{
          ...linkFixture,
          resolved: true,
          target_note_id: 'note:two',
          target_note_title: 'Two',
          target_relative_path: 'pages/two.md',
          ...linkOverrides,
        }],
      }),
    } as never)

    await expect(vaultApi.page('vault:one', 'note:one'))
      .rejects.toMatchObject({ code: 'page-invalid' })
  })

  it('rejects a link whose source range is reversed', async () => {
    mockedGet.mockResolvedValueOnce({
      data: pageFixture({
        outgoing_links: [{
          ...linkFixture,
          source_start: 8,
          source_end: 7,
        }],
      }),
    } as never)

    await expect(vaultApi.page('vault:one', 'note:one'))
      .rejects.toMatchObject({ code: 'page-invalid' })
  })

  it('translates the orphaned-note API error', async () => {
    mockedGet.mockRejectedValueOnce({
      isAxiosError: true,
      response: {
        status: 409,
        data: {
          detail: { code: 'vault_canonical_file_unavailable' },
        },
      },
    })

    await expect(vaultApi.page('vault:one', 'note:one'))
      .rejects.toMatchObject({ code: 'canonical-path-unavailable' })
  })

  it('translates the invalid-page API error', async () => {
    mockedGet.mockRejectedValueOnce({
      isAxiosError: true,
      response: {
        status: 409,
        data: {
          detail: { code: 'vault_page_invalid' },
        },
      },
    })

    await expect(vaultApi.page('vault:one', 'note:one'))
      .rejects.toMatchObject({ code: 'page-invalid' })
  })

  it('does not translate unrelated API failures', async () => {
    const error = {
      isAxiosError: true,
      response: {
        status: 500,
        data: { detail: { code: 'database_unavailable' } },
      },
    }
    mockedGet.mockRejectedValueOnce(error)

    await expect(vaultApi.page('vault:one', 'note:one')).rejects.toBe(error)
  })

  it('accepts a resolved link with a present empty canonical title', async () => {
    mockedGet.mockResolvedValueOnce({
      data: pageFixture({
        outgoing_links: [{
          ...linkFixture,
          resolved: true,
          target_note_id: 'note:two',
          target_note_title: '',
          target_relative_path: 'pages/two.md',
        }],
      }),
    } as never)

    await expect(vaultApi.page('vault:one', 'note:one'))
      .resolves.toMatchObject({
        outgoing_links: [expect.objectContaining({ target_note_title: '' })],
      })
  })
})

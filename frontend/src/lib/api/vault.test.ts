import { describe, expect, it, vi } from 'vitest'

vi.mock('./client', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

import apiClient from './client'
import { vaultApi, vaultFileSchema } from './vault'

const file = {
  id: 'vault_file:one', vault_id: 'vault_mount:one', relative_path: 'Projects/Plan.md',
  note_id: 'note:real-projection-id',
  file_kind: 'markdown', format: 'obsidian', content_hash: 'abc', parse_status: 'parsed',
}

describe('vault API boundary', () => {
  it('validates a vault file before exposing it to callers', () => {
    expect(vaultFileSchema.parse(file)).toMatchObject(file)
    expect(() => vaultFileSchema.parse({ ...file, note_id: undefined })).toThrow()
    expect(() => vaultFileSchema.parse({ ...file, parse_status: 'unknown' })).toThrow()
  })

  it.each([
    '/Users/owner/secret.md',
    'C:\\Users\\owner\\secret.md',
    '\\\\server\\share\\secret.md',
    '//server/share/secret.md',
  ])('rejects POSIX, drive, and UNC absolute paths from file responses: %s', async (relative_path) => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [{ ...file, relative_path }] } as never)
    await expect(vaultApi.files('vault_mount:one')).rejects.toThrow(/absolute path/i)
  })

  it('rejects absolute paths from page and graph responses', async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { note: { id: 'note:one', source_path: '/Users/owner/secret.md' }, blocks: [], tasks: [], outgoing_links: [], backlinks: [] } } as never)
      .mockResolvedValueOnce({ data: { nodes: [{ id: '/Users/owner/secret.md', title: 'Secret', source_format: 'obsidian' }], edges: [] } } as never)

    await expect(vaultApi.page('vault_mount:one', 'note:one')).rejects.toThrow(/absolute path/i)
    await expect(vaultApi.graph('vault_mount:one', 'note:one')).rejects.toThrow(/absolute path/i)
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { VaultFileTree } from './VaultFileTree'

describe('VaultFileTree', () => {
  it('filters files and opens a selected note', () => {
    const onSelect = vi.fn()
    render(<VaultFileTree files={[{
      id: 'vault_file:one',
      note_id: 'note:actual-derived-id',
      vault_id: 'v',
      relative_path: 'Projects/Plan.md',
      file_kind: 'markdown',
      format: 'obsidian',
      content_hash: null,
      parse_status: 'parsed',
      size_bytes: 128,
      modified_ns: 1_000,
      encoding: 'utf-8',
      newline: 'lf',
      deleted_state: 'present',
    }]} selectedNoteId="" onSelect={onSelect} />)
    fireEvent.change(screen.getByRole('textbox', { name: 'knowledge.filterFiles' }), { target: { value: 'plan' } })
    fireEvent.click(screen.getByRole('treeitem', { name: 'Projects/Plan.md' }))
    expect(onSelect).toHaveBeenCalledWith('note:actual-derived-id')
  })
})

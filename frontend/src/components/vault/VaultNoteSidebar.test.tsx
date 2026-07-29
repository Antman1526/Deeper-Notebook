import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { VaultPage } from '@/lib/api/vault'
import { buildMarkdownModel } from '@/lib/vault/markdown-model'

import { VaultNoteSidebar } from './VaultNoteSidebar'

const pageFixture = {
  file: { id: 'file:plan', note_id: 'note:plan', vault_id: 'vault:one', relative_path: 'pages/plan.md', file_kind: 'markdown', format: 'markdown', content_hash: 'f'.repeat(64), parse_status: 'parsed', size_bytes: 1, modified_ns: 1, encoding: 'utf-8', newline: 'lf', deleted_state: 'present' },
  note: { id: 'note:plan', properties: { Zebra: ['late'], alpha: 'first' }, tags: ['Research'] },
  blocks: [], tasks: [], outgoing_links: [], backlinks: [],
} satisfies VaultPage

describe('VaultNoteSidebar', () => {
  it('announces heading levels and navigates duplicate slugs', () => {
    const onHeading = vi.fn()
    render(
      <VaultNoteSidebar
        model={buildMarkdownModel('# Plan\n## Evidence\n# Plan')}
        page={pageFixture}
        onHeading={onHeading}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Level 2 Evidence' }))
    expect(onHeading).toHaveBeenCalledWith(expect.objectContaining({ slug: 'evidence', level: 2 }))
    expect(screen.getByText('pages/plan.md')).toBeInTheDocument()
    expect(screen.getByText('#research')).toBeInTheDocument()
  })
})

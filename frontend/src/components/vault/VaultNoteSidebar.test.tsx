import { fireEvent, render, screen, within } from '@testing-library/react'
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
    expect(screen.getByText('#Research')).toBeInTheDocument()
  })

  it('uses deterministic ordering, preserves tag casing, and deduplicates exact tags', () => {
    const page = {
      ...pageFixture,
      note: {
        ...pageFixture.note,
        properties: { alpha: 1, Alpha: 2, zebra: 3 },
        tags: ['beta', 'Beta', 'beta'],
      },
    } satisfies VaultPage
    render(<VaultNoteSidebar model={buildMarkdownModel('')} page={page} onHeading={vi.fn()} />)

    const properties = screen.getByRole('region', { name: 'Properties' })
    expect(within(properties).getAllByRole('term').map((term) => term.textContent)).toEqual(['Alpha', 'alpha', 'zebra'])
    const tags = screen.getByRole('region', { name: 'Tags' })
    expect(within(tags).getAllByRole('listitem').map((tag) => tag.textContent)).toEqual(['#Beta', '#beta'])
  })

  it('formats hostile structured properties safely within the output budget', () => {
    const circular: Record<string, unknown> = { name: 'loop' }
    circular.self = circular
    const throwing = Object.defineProperty({}, 'boom', {
      enumerable: true,
      get() { throw new Error('nope') },
    })
    let indexedReads = 0
    const huge = new Proxy(Array.from({ length: 10_000 }, () => 'x'.repeat(400)), {
      get(target, property, receiver) {
        if (typeof property === 'string' && /^\d+$/.test(property)) indexedReads += 1
        return Reflect.get(target, property, receiver)
      },
    })
    const page = {
      ...pageFixture,
      note: { ...pageFixture.note, properties: { circular, throwing, huge } },
    } satisfies VaultPage

    render(<VaultNoteSidebar model={buildMarkdownModel('')} page={page} onHeading={vi.fn()} />)

    const values = screen.getAllByRole('definition').map((definition) => definition.textContent || '')
    expect(values.every((value) => value.length <= 2_000)).toBe(true)
    expect(values.some((value) => value.includes('[Circular]'))).toBe(true)
    expect(values.some((value) => value.includes('[Unserializable]'))).toBe(true)
    expect(indexedReads).toBeLessThan(20)
  })
})

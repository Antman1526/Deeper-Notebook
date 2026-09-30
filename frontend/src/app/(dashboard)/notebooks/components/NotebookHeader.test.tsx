import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { NotebookResponse } from '@/lib/types/api'

import { NotebookHeader } from './NotebookHeader'

// T0-12 — the header rendered "Created 9 months ago •Updated 9 months ago" (JSX
// trims the space before a line break, so the bullet touched "Updated"), and the
// description broke in the middle of a word on narrow screens ("wit / h").

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'common.created': 'Created {time}',
      'common.updated': 'Updated {time}',
    }[key] ?? key),
    language: 'en-US',
  }),
}))
vi.mock('@/lib/hooks/use-notebooks', () => ({
  useUpdateNotebook: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
}))
vi.mock('./NotebookDeleteDialog', () => ({ NotebookDeleteDialog: () => null }))
vi.mock('./ExportNotebookDialog', () => ({ ExportNotebookDialog: () => null }))
vi.mock('@/components/notebooks/ExecutiveSynthesisDialog', () => ({ ExecutiveSynthesisDialog: () => null }))
vi.mock('@/components/notebooks/MindMapButton', () => ({ MindMapButton: () => <button type="button">Mind map</button> }))

const notebook: NotebookResponse = {
  id: 'notebook:abc',
  name: 'Deterministic Research Notebook',
  description: 'A browser-harness notebook with fixed evidence.',
  archived: false,
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-02T00:00:00Z',
  source_count: 1,
  note_count: 0,
}

describe('NotebookHeader', () => {
  it('separates the created and updated times with a spaced bullet', () => {
    render(<NotebookHeader notebook={notebook} />)

    const meta = screen.getByText(/^Created .* • Updated /)
    expect(meta.textContent).toMatch(/ago • Updated .* ago$/)
  })

  it('wraps the description at word boundaries instead of inside words', () => {
    render(<NotebookHeader notebook={notebook} />)

    const description = screen.getByRole('button', { name: notebook.description })
    expect(description.className).toContain('[overflow-wrap:anywhere]')
    expect(description.className).not.toContain('break-all')
  })
})

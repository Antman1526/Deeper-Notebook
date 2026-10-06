import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { NotebookResponse } from '@/lib/types/api'

import { NotebookCard } from './NotebookCard'

// T0-6 — the notebook tile used to be a click-only <div>: no link, no role, no
// tabindex, no key handler, so a keyboard or screen-reader user could not open a
// notebook from the default grid. The title is now a real link stretched over
// the whole card, so mouse behaviour is unchanged.

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    language: 'en-US',
  }),
}))
vi.mock('@/lib/hooks/use-notebooks', () => ({
  useUpdateNotebook: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/lib/stores/podcast-studio-store', () => ({
  usePodcastStudioStore: (selector: (state: { open: () => void }) => unknown) => selector({ open: vi.fn() }),
}))
vi.mock('@/components/podcasts/TurnIntoPodcastAction', () => ({
  TurnIntoPodcastAction: () => <button type="button">Turn into podcast</button>,
}))
vi.mock('./NotebookDeleteDialog', () => ({ NotebookDeleteDialog: () => null }))

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

describe('NotebookCard keyboard access', () => {
  it('exposes the notebook as a real link to its workspace', () => {
    render(<NotebookCard notebook={notebook} />)

    const link = screen.getByRole('link', { name: 'Deterministic Research Notebook' })
    expect(link).toHaveAttribute('href', '/notebooks/notebook%3Aabc')
  })

  it('lays the link over the whole cover, outside the label', () => {
    const { container } = render(<NotebookCard notebook={notebook} />)

    const link = screen.getByRole('link', { name: 'Deterministic Research Notebook' })
    const root = container.firstElementChild as HTMLElement
    // v0.8.130 — the book's cover is the whole clickable face: the link is a direct
    // child of the cover (itself a direct child of the positioned root), so `inset-0`
    // spans the WHOLE book. Inside CardHeader it would be sized by that header (a
    // size container).
    const cover = root.querySelector('[data-dn-book-cover]') as HTMLElement
    expect(cover.parentElement).toBe(root)
    expect(link.parentElement).toBe(cover)
    expect(link.closest('[data-slot="card"]')).toBeNull()
    expect(root.className).toContain('relative')
    expect(link.className).toContain('absolute')
    expect(link.className).toContain('inset-0')
  })

  it('keeps the title as plain text so a long name is clamped, not cut mid-line', () => {
    render(<NotebookCard notebook={notebook} />)

    const title = document.querySelector('[data-slot="card-title"]')
    expect(title).toHaveTextContent('Deterministic Research Notebook')
    expect(title?.querySelector('a')).toBeNull()
    // v0.8.130 — the label carries the whole name on up to three lines (it used to
    // truncate to one); a link inside the title would stop the clamp working.
    expect(title?.className).toContain('line-clamp-3')
  })

  it('keeps the actions menu and podcast action above the overlay link', () => {
    render(<NotebookCard notebook={notebook} />)

    const link = screen.getByRole('link', { name: 'Deterministic Research Notebook' })
    expect(link.className).toMatch(/z-\[1\]/)
    expect(screen.getByRole('button', { name: 'notebooks.notebookCard.actionsFor' }).className)
      .toContain('z-10')
    // The podcast action sits in the cover's footer, which is raised above the link.
    expect(screen.getByRole('button', { name: 'Turn into podcast' }).closest('[data-dn-cover-footer]')?.className)
      .toContain('z-10')
  })

  // v0.8.130 — the stationery layer.
  it('binds the notebook in a cloth chosen from its id, with its initial stamped on the cover', () => {
    const { container } = render(<NotebookCard notebook={notebook} />)
    const root = container.firstElementChild as HTMLElement
    expect(['ink', 'forest', 'oxblood', 'ochre', 'slate', 'plum']).toContain(root.getAttribute('data-dn-cover'))
    const monogram = root.querySelector('[data-dn-book-monogram]')
    // Drawn by CSS from the attribute: ornament, with no text in the document.
    expect(monogram).toHaveAttribute('data-dn-book-monogram', 'D')
    expect(monogram).toBeEmptyDOMElement()
    // Decoration stays out of the accessibility tree.
    expect(monogram).toHaveAttribute('aria-hidden', 'true')
    expect(root.querySelector('[data-dn-book-pages]')).toHaveAttribute('aria-hidden', 'true')
    expect(root.querySelector('[data-dn-book-ribbon]')).toHaveAttribute('aria-hidden', 'true')
  })
})

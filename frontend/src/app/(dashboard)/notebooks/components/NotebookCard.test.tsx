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

  it('lays the link over the whole card as a direct child of the card root', () => {
    const { container } = render(<NotebookCard notebook={notebook} />)

    const link = screen.getByRole('link', { name: 'Deterministic Research Notebook' })
    const root = container.firstElementChild as HTMLElement
    // A direct child of the positioned root, so `inset-0` spans the WHOLE card.
    // Inside CardHeader it would be sized by that header (a size container).
    expect(link.parentElement).toBe(root)
    expect(root.className).toContain('relative')
    expect(link.className).toContain('absolute')
    expect(link.className).toContain('inset-0')
  })

  it('keeps the title as plain text so a long name can still truncate', () => {
    render(<NotebookCard notebook={notebook} />)

    const title = document.querySelector('[data-slot="card-title"]')
    expect(title).toHaveTextContent('Deterministic Research Notebook')
    expect(title?.querySelector('a')).toBeNull()
    expect(title?.className).toContain('truncate')
  })

  it('keeps the actions menu and podcast action above the overlay link', () => {
    render(<NotebookCard notebook={notebook} />)

    const link = screen.getByRole('link', { name: 'Deterministic Research Notebook' })
    expect(link.className).toMatch(/z-\[1\]/)
    expect(screen.getByRole('button', { name: 'Actions for Deterministic Research Notebook' }).className)
      .toContain('z-10')
    expect(screen.getByRole('button', { name: 'Turn into podcast' }).parentElement?.className)
      .toContain('z-10')
  })
})

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const overlay = vi.hoisted(() => ({
  create: vi.fn(),
  reset: vi.fn(),
  isPending: false,
  error: null as Error | null,
  renderCount: 0,
  resetRerendersRemaining: 0,
}))

vi.mock('@/lib/hooks/use-overlay', async () => {
  const { useCallback, useReducer } = await import('react')

  return {
    useCreateUniqueOverlayNote: () => {
      const [, forceRender] = useReducer((count: number) => count + 1, 0)
      const reset = useCallback(() => {
        overlay.reset()
        if (overlay.resetRerendersRemaining > 0) {
          overlay.resetRerendersRemaining -= 1
          forceRender()
        }
      }, [forceRender])

      overlay.renderCount += 1
      return { mutateAsync: overlay.create, reset, isPending: overlay.isPending, error: overlay.error }
    },
  }
})
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'knowledge.overlay.newUnique': 'New unique note',
      'knowledge.overlay.uniqueTitle': 'Unique note title',
      'knowledge.overlay.create': 'Create note',
      'knowledge.overlay.creating': 'Creating note…',
      'knowledge.overlay.createError': 'The overlay note could not be created.',
      'common.cancel': 'Cancel',
    }[key] || key),
  }),
}))

import { CreateUniqueNoteDialog } from './CreateUniqueNoteDialog'

const page = {
  overlay: {
    id: 'overlay_note:unique', source_authority: 'overlay' as const,
    space_id: 'overlay_space:default', projected_note_id: 'note:unique',
    stable_id: 'a'.repeat(20), kind: 'unique' as const, date_key: null,
    relative_path: 'Notes/Research Idea.md', title: 'Research Idea',
    content_hash: 'a'.repeat(64), revision: 1, projection_state: 'current' as const,
    encoding: 'utf-8' as const, newline: 'lf' as const,
    created_at: '2026-07-29T00:00:00.000Z', updated_at: '2026-07-29T00:00:00.000Z',
  },
  note: { id: 'note:unique', title: 'Research Idea', content: '', properties: {}, tags: [] },
  blocks: [], tasks: [], outgoing_links: [], backlinks: [], graph: null,
}

describe('CreateUniqueNoteDialog', () => {
  beforeEach(() => {
    overlay.create.mockReset()
    overlay.reset.mockReset()
    overlay.reset.mockImplementation(() => { overlay.error = null })
    overlay.create.mockResolvedValue(page)
    overlay.error = null
    overlay.renderCount = 0
    overlay.resetRerendersRemaining = 0
  })

  it('trims the title, sends one idempotency key, and opens the result', async () => {
    const onOpen = vi.fn()
    render(<CreateUniqueNoteDialog open onOpenChange={vi.fn()} onOpen={onOpen} />)

    fireEvent.change(screen.getByLabelText('Unique note title'), { target: { value: '  Research Idea  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create note' }))

    await waitFor(() => expect(overlay.create).toHaveBeenCalledWith({
      title: 'Research Idea', idempotencyKey: expect.stringMatching(/^unique-/),
    }))
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({
      sourceAuthority: 'overlay', noteId: 'overlay_note:unique', viewMode: 'source',
    }))
  })

  it('reuses the idempotency key for a safe retry and renews it after reopen', async () => {
    overlay.create.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(page)
    const onOpenChange = vi.fn()
    const view = render(<CreateUniqueNoteDialog open onOpenChange={onOpenChange} onOpen={vi.fn()} />)
    const input = screen.getByLabelText('Unique note title')
    fireEvent.change(input, { target: { value: 'Retry me' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create note' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('The overlay note could not be created.'))
    fireEvent.click(screen.getByRole('button', { name: 'Create note' }))
    await waitFor(() => expect(overlay.create).toHaveBeenCalledTimes(2))
    expect(overlay.create.mock.calls[1][0].idempotencyKey).toBe(overlay.create.mock.calls[0][0].idempotencyKey)

    view.rerender(<CreateUniqueNoteDialog open={false} onOpenChange={onOpenChange} onOpen={vi.fn()} />)
    view.rerender(<CreateUniqueNoteDialog open onOpenChange={onOpenChange} onOpen={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Unique note title'), { target: { value: 'Another note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create note' }))
    await waitFor(() => expect(overlay.create).toHaveBeenCalledTimes(3))
    expect(overlay.create.mock.calls[2][0].idempotencyKey).not.toBe(overlay.create.mock.calls[0][0].idempotencyKey)
  })

  it('uses the shared dialog primitive for keyboard dismissal and labeled focus', async () => {
    const onOpenChange = vi.fn()
    render(<CreateUniqueNoteDialog open onOpenChange={onOpenChange} onOpen={vi.fn()} />)

    expect(screen.getByLabelText('Unique note title')).toHaveFocus()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
  })

  it('clears a mutation error after close and reopen while preserving retry identity while open', async () => {
    overlay.create.mockRejectedValueOnce(new Error('offline'))
    const onOpenChange = vi.fn()
    const view = render(<CreateUniqueNoteDialog open onOpenChange={onOpenChange} onOpen={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Unique note title'), { target: { value: 'Retry me' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create note' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    overlay.error = new Error('stale mutation error')

    view.rerender(<CreateUniqueNoteDialog open={false} onOpenChange={onOpenChange} onOpen={vi.fn()} />)
    view.rerender(<CreateUniqueNoteDialog open onOpenChange={onOpenChange} onOpen={vi.fn()} />)
    expect(screen.queryByRole('alert')).toBeNull()
    expect(overlay.reset).toHaveBeenCalled()
  })

  it('settles mutation rerenders and resets once per open or close transition', async () => {
    overlay.resetRerendersRemaining = 6
    const view = render(<CreateUniqueNoteDialog open onOpenChange={vi.fn()} onOpen={vi.fn()} />)

    await waitFor(() => expect(overlay.reset).toHaveBeenCalledTimes(1))
    expect(overlay.renderCount).toBeGreaterThan(1)

    view.rerender(<CreateUniqueNoteDialog open={false} onOpenChange={vi.fn()} onOpen={vi.fn()} />)
    await waitFor(() => expect(overlay.reset).toHaveBeenCalledTimes(2))

    view.rerender(<CreateUniqueNoteDialog open onOpenChange={vi.fn()} onOpen={vi.fn()} />)
    await waitFor(() => expect(overlay.reset).toHaveBeenCalledTimes(3))
  })
})

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const overlay = vi.hoisted(() => ({
  notes: [] as Array<{ id: string; source_authority: 'overlay'; space_id: string; projected_note_id: string; stable_id: string; kind: 'daily' | 'unique'; date_key: string | null; relative_path: string; title: string; content_hash: string; revision: number; projection_state: 'current'; encoding: 'utf-8'; newline: 'lf'; created_at: string; updated_at: string }>,
  daily: vi.fn(),
  isLoading: false,
  isError: false,
  error: null as Error | null,
}))

vi.mock('@/lib/hooks/use-overlay', () => ({
  useOverlayNotes: () => ({
    data: overlay.notes,
    isLoading: overlay.isLoading,
    isError: overlay.isError,
    error: overlay.error,
  }),
  useTodayOverlayNote: () => ({ mutateAsync: overlay.daily, isPending: false }),
}))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'knowledge.overlay.name': 'Deeper Notebook Overlay',
      'knowledge.overlay.writable': 'Writable app-owned note',
      'knowledge.overlay.today': 'Today',
      'knowledge.overlay.newUnique': 'New unique note',
      'knowledge.overlay.empty': 'No overlay notes yet',
      'knowledge.overlay.loadError': 'Overlay notes could not be loaded.',
    }[key] || key),
  }),
}))

import { OverlayUtilityPanel, localDateKey } from './OverlayUtilityPanel'

const page = {
  overlay: {
    id: 'overlay_note:daily', source_authority: 'overlay' as const,
    space_id: 'overlay_space:default', projected_note_id: 'note:daily',
    stable_id: 'a'.repeat(20), kind: 'daily' as const, date_key: '2026-07-29',
    relative_path: 'Daily/2026-07-29.md', title: '2026-07-29',
    content_hash: 'a'.repeat(64), revision: 1, projection_state: 'current' as const,
    encoding: 'utf-8' as const, newline: 'lf' as const,
    created_at: '2026-07-29T00:00:00.000Z', updated_at: '2026-07-29T00:00:00.000Z',
  },
  note: { id: 'note:daily', title: '2026-07-29', content: '', properties: {}, tags: [] },
  blocks: [], tasks: [], outgoing_links: [], backlinks: [], graph: null,
}

describe('OverlayUtilityPanel', () => {
  beforeEach(() => {
    overlay.notes = []
    overlay.daily.mockReset()
    overlay.daily.mockResolvedValue(page)
    overlay.isLoading = false
    overlay.isError = false
  })

  it('opens the one returned daily note as an overlay tab', async () => {
    const onOpen = vi.fn()
    render(<OverlayUtilityPanel onOpen={onOpen} onNewUnique={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Today' }))

    await waitFor(() => expect(overlay.daily).toHaveBeenCalledWith(localDateKey()))
    expect(onOpen).toHaveBeenCalledWith({
      sourceAuthority: 'overlay',
      vaultId: 'overlay_space:default',
      noteId: 'overlay_note:daily',
      title: '2026-07-29',
      relativePath: 'Daily/2026-07-29.md',
      viewMode: 'source',
    })
  })

  it('keeps its empty and error states independently visible', () => {
    overlay.isError = true
    render(<OverlayUtilityPanel onOpen={vi.fn()} onNewUnique={vi.fn()} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Overlay notes could not be loaded.')
    expect(screen.getByText('No overlay notes yet')).toBeInTheDocument()
  })

  it('uses a locale-independent local calendar date key', () => {
    expect(localDateKey(new Date(2026, 6, 9, 23, 59))).toBe('2026-07-09')
  })
})

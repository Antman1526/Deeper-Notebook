import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const overlay = vi.hoisted(() => ({
  notes: [] as Array<{ id: string; source_authority: 'overlay'; space_id: string; projected_note_id: string; stable_id: string; kind: 'daily' | 'unique'; date_key: string | null; relative_path: string; title: string; content_hash: string; revision: number; projection_state: 'current'; encoding: 'utf-8'; newline: 'lf'; created_at: string; updated_at: string }>,
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
      'knowledge.overlay.createError': 'The overlay note could not be created.',
      'knowledge.overlay.daily': 'Daily',
      'knowledge.overlay.notes': 'Notes',
    }[key] || key),
  }),
}))

import { OverlayUtilityPanel, localDateKey, tabFromOverlay } from './OverlayUtilityPanel'

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
  editable_markdown: '# 2026-07-29\n',
  note: { id: 'note:daily', title: '2026-07-29', content: '', properties: {}, tags: [] },
  blocks: [], tasks: [], outgoing_links: [], backlinks: [], graph: null,
}

describe('OverlayUtilityPanel', () => {
  beforeEach(() => {
    overlay.notes = []
    overlay.isLoading = false
    overlay.isError = false
  })

  it('uses the parent Today callback and opens its returned overlay tab', async () => {
    const onOpen = vi.fn()
    const onToday = vi.fn(async () => onOpen(tabFromOverlay(page)))
    render(<OverlayUtilityPanel onOpen={onOpen} onNewUnique={vi.fn()} onToday={onToday} />)

    fireEvent.click(screen.getByRole('button', { name: 'Today' }))

    await waitFor(() => expect(onToday).toHaveBeenCalledOnce())
    expect(onOpen).toHaveBeenCalledWith({
      sourceAuthority: 'overlay',
      vaultId: 'overlay_space:default',
      noteId: 'overlay_note:daily',
      title: '2026-07-29',
      relativePath: 'Daily/2026-07-29.md',
      viewMode: 'source',
    })
  })

  it('disables Today while the parent mutation is pending', () => {
    render(<OverlayUtilityPanel onOpen={vi.fn()} onNewUnique={vi.fn()} onToday={vi.fn(async () => undefined)} todayPending />)

    expect(screen.getByRole('button', { name: 'Today' })).toBeDisabled()
  })

  it('catches a rejected parent Today callback and announces an assertive error', async () => {
    render(<OverlayUtilityPanel
      onOpen={vi.fn()}
      onNewUnique={vi.fn()}
      onToday={vi.fn(async () => { throw new Error('offline') })}
    />)

    fireEvent.click(screen.getByRole('button', { name: 'Today' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The overlay note could not be created.')
  })

  it('keeps its empty and error states independently visible', () => {
    overlay.isError = true
    render(<OverlayUtilityPanel onOpen={vi.fn()} onNewUnique={vi.fn()} onToday={vi.fn(async () => undefined)} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Overlay notes could not be loaded.')
    expect(screen.getByText('No overlay notes yet')).toBeInTheDocument()
  })

  it('uses a locale-independent local calendar date key', () => {
    expect(localDateKey(new Date(2026, 6, 9, 23, 59))).toBe('2026-07-09')
  })
})

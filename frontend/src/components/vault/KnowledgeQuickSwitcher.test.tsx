import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  requestCommandSurface,
  resetCommandSurfaceStore,
  useCommandSurfaceStore,
} from '@/lib/commands/command-surface-store'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'

const catalog = vi.hoisted(() => ({
  candidates: [
    {
      key: 'vault:fixture\\0note:evidence',
      sourceAuthority: 'external-vault' as const,
      vaultId: 'vault:fixture',
      noteId: 'note:evidence',
      vaultName: 'Fixture vault',
      format: 'markdown' as const,
      title: 'Evidence',
      relativePath: 'notes/evidence.md',
      isOpen: false,
    },
    {
      key: 'vault:fixture\\0note:plan',
      sourceAuthority: 'external-vault' as const,
      vaultId: 'vault:fixture',
      noteId: 'note:plan',
      vaultName: 'Fixture vault',
      format: 'markdown' as const,
      title: 'Plan',
      relativePath: 'notes/plan.md',
      isOpen: true,
    },
  ],
  isLoading: false,
  failedVaultCount: 0,
  retryFailedVaults: vi.fn(async () => undefined),
}))
const overlay = vi.hoisted(() => ({
  notes: [] as Array<{
    id: string; source_authority: 'overlay'; space_id: string; projected_note_id: string; stable_id: string
    kind: 'daily' | 'unique'; date_key: string | null; relative_path: string; title: string; content_hash: string
    revision: number; projection_state: 'current'; encoding: 'utf-8'; newline: 'lf'; created_at: string; updated_at: string
  }>,
}))

vi.mock('@/lib/hooks/use-knowledge-command-data', () => ({
  useKnowledgeCatalog: () => catalog,
}))
vi.mock('@/lib/hooks/use-overlay', () => ({
  useOverlayNotes: () => ({ data: overlay.notes, isLoading: false, isError: false }),
}))

import { KnowledgeQuickSwitcher } from './KnowledgeQuickSwitcher'

describe('KnowledgeQuickSwitcher', () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollIntoView = vi.fn()
    resetCommandSurfaceStore()
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
    catalog.isLoading = false
    catalog.failedVaultCount = 0
    catalog.candidates = [
      {
        key: 'vault:fixture\\0note:evidence', sourceAuthority: 'external-vault',
        vaultId: 'vault:fixture', noteId: 'note:evidence', vaultName: 'Fixture vault',
        format: 'markdown', title: 'Evidence', relativePath: 'notes/evidence.md', isOpen: false,
      },
      {
        key: 'vault:fixture\\0note:plan', sourceAuthority: 'external-vault',
        vaultId: 'vault:fixture', noteId: 'note:plan', vaultName: 'Fixture vault',
        format: 'markdown', title: 'Plan', relativePath: 'notes/plan.md', isOpen: true,
      },
    ]
    overlay.notes = []
    catalog.retryFailedVaults.mockClear()
  })

  it('keeps an overlay candidate distinct from an external note with the same title', async () => {
    overlay.notes = [{
      id: 'note:evidence', source_authority: 'overlay', space_id: 'overlay_space:default',
      projected_note_id: 'projected:evidence', stable_id: 'a'.repeat(20), kind: 'unique', date_key: null,
      relative_path: 'Notes/Evidence.md', title: 'Evidence', content_hash: 'a'.repeat(64), revision: 1,
      projection_state: 'current', encoding: 'utf-8', newline: 'lf',
      created_at: '2026-07-29T00:00:00.000Z', updated_at: '2026-07-29T00:00:00.000Z',
    }]
    render(<KnowledgeQuickSwitcher mounts={[]} />)
    act(() => requestCommandSurface('quick-switcher', 'evidence'))
    const dialog = await screen.findByRole('dialog', { name: 'knowledge.quickSwitcher' })
    expect(within(dialog).getAllByRole('option', { name: /Evidence/ })).toHaveLength(2)
    fireEvent.click(within(dialog).getAllByRole('option', { name: /Evidence/ })[0])
    await waitFor(() => expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs.at(-1))
      .toMatchObject({ sourceAuthority: 'overlay', vaultId: 'overlay_space:default' }))
  })

  it('keeps healthy overlay results available for keyboard selection while external catalogs load', async () => {
    catalog.candidates = []
    catalog.isLoading = true
    overlay.notes = [{
      id: 'overlay_note:daily', source_authority: 'overlay', space_id: 'overlay_space:default',
      projected_note_id: 'projected:daily', stable_id: 'a'.repeat(20), kind: 'daily', date_key: '2026-07-29',
      relative_path: 'Daily/2026-07-29.md', title: '2026-07-29', content_hash: 'a'.repeat(64), revision: 1,
      projection_state: 'current', encoding: 'utf-8', newline: 'lf',
      created_at: '2026-07-29T00:00:00.000Z', updated_at: '2026-07-29T00:00:00.000Z',
    }]
    render(<KnowledgeQuickSwitcher mounts={[]} />)
    act(() => requestCommandSurface('quick-switcher'))
    const dialog = await screen.findByRole('dialog', { name: 'knowledge.quickSwitcher' })
    const input = within(dialog).getByRole('combobox')

    expect(within(dialog).getByRole('option', { name: /2026-07-29/ })).toBeInTheDocument()
    expect(within(dialog).getByRole('status')).toHaveTextContent('knowledge.filesLoading')
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs.at(-1))
      .toMatchObject({ sourceAuthority: 'overlay', noteId: 'overlay_note:daily' }))
  })

  it('ranks notes and opens the selected note in the active pane', async () => {
    render(<KnowledgeQuickSwitcher mounts={[]} />)
    act(() => requestCommandSurface('quick-switcher'))
    const dialog = await screen.findByRole('dialog', { name: 'knowledge.quickSwitcher' })
    fireEvent.change(within(dialog).getByRole('combobox'), {
      target: { value: 'evidence' },
    })
    fireEvent.click(within(dialog).getByRole('option', { name: /Evidence/ }))

    await waitFor(() => {
      const state = useKnowledgeWorkspaceStore.getState()
      expect(state.panes[state.activePaneId].tabs.at(-1)).toMatchObject({
        vaultId: 'vault:fixture',
        noteId: 'note:evidence',
      })
    })
  })

  it('restores invoker focus after closing', async () => {
    const invoker = document.createElement('button')
    document.body.append(invoker)
    render(<KnowledgeQuickSwitcher mounts={[]} />)
    act(() => requestCommandSurface('quick-switcher', '', invoker))
    const dialog = await screen.findByRole('dialog', { name: 'knowledge.quickSwitcher' })
    fireEvent.keyDown(within(dialog).getByRole('combobox'), { key: 'Escape' })
    await waitFor(() => expect(document.activeElement).toBe(invoker))
    invoker.remove()
  })

  it('keeps healthy results visible and retries only failed catalogs', async () => {
    catalog.failedVaultCount = 1
    render(<KnowledgeQuickSwitcher mounts={[]} />)
    act(() => requestCommandSurface('quick-switcher'))
    const dialog = await screen.findByRole('dialog', { name: 'knowledge.quickSwitcher' })
    expect(within(dialog).getAllByText('knowledge.partialCatalogFailure'))
      .toHaveLength(2)
    expect(within(dialog).getByRole('option', { name: /Evidence/ })).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.retry' }))
    await waitFor(() => expect(catalog.retryFailedVaults).toHaveBeenCalledOnce())
  })

  it('keeps a persistent live status through loading and partial failure transitions', async () => {
    catalog.isLoading = true
    const { rerender } = render(<KnowledgeQuickSwitcher mounts={[]} />)
    act(() => requestCommandSurface('quick-switcher'))
    const status = await screen.findByRole('status')
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(status).toHaveTextContent('knowledge.filesLoading')

    catalog.isLoading = false
    catalog.failedVaultCount = 1
    rerender(<KnowledgeQuickSwitcher mounts={[]} />)
    expect(screen.getByRole('status')).toBe(status)
    expect(status).toHaveTextContent('knowledge.partialCatalogFailure')
  })

  it('announces no matches and marks already-open results', async () => {
    render(<KnowledgeQuickSwitcher mounts={[]} />)
    act(() => requestCommandSurface('quick-switcher', 'missing'))
    const dialog = await screen.findByRole('dialog', { name: 'knowledge.quickSwitcher' })
    expect(within(dialog).getByRole('status')).toHaveTextContent('knowledge.noMatchingFiles')

    fireEvent.change(within(dialog).getByRole('combobox'), {
      target: { value: 'plan' },
    })
    expect(within(dialog).getByRole('option', { name: /Plan/ }))
      .toHaveTextContent('knowledge.alreadyOpen')
  })

  it('offers a keyboard-reachable bookmark search action without opening a tab', async () => {
    const onBookmarkSearch = vi.fn()
    render(<KnowledgeQuickSwitcher mounts={[]} onBookmarkSearch={onBookmarkSearch} />)
    act(() => requestCommandSurface('quick-switcher', 'evidence'))
    const dialog = await screen.findByRole('dialog', { name: 'knowledge.quickSwitcher' })

    fireEvent.click(within(dialog).getByRole('option', { name: 'Bookmark search for evidence' }))

    expect(onBookmarkSearch).toHaveBeenCalledWith('evidence', 'text')
    expect(useKnowledgeWorkspaceStore.getState().panes['pane-1'].tabs).toHaveLength(0)
  })

  it('preserves the active semantic search mode in a bookmark action', async () => {
    const onBookmarkSearch = vi.fn()
    render(<KnowledgeQuickSwitcher mounts={[]} searchMode="semantic" onBookmarkSearch={onBookmarkSearch} />)
    act(() => requestCommandSurface('quick-switcher', 'evidence'))
    const dialog = await screen.findByRole('dialog', { name: 'knowledge.quickSwitcher' })

    fireEvent.click(within(dialog).getByRole('option', { name: 'Bookmark search for evidence' }))

    expect(onBookmarkSearch).toHaveBeenCalledWith('evidence', 'semantic')
  })

  it('consumes its request without losing local invoker restoration or replaying on remount', async () => {
    const invoker = document.createElement('button')
    document.body.append(invoker)
    const first = render(<KnowledgeQuickSwitcher mounts={[]} />)
    act(() => requestCommandSurface('quick-switcher', '', invoker))
    const dialog = await screen.findByRole('dialog', { name: 'knowledge.quickSwitcher' })
    expect(useCommandSurfaceStore.getState()).toMatchObject({
      kind: null,
      initialQuery: '',
      invoker: null,
    })
    fireEvent.keyDown(within(dialog).getByRole('combobox'), { key: 'Escape' })
    await waitFor(() => expect(invoker).toHaveFocus())

    first.unmount()
    render(<KnowledgeQuickSwitcher mounts={[]} />)
    expect(screen.queryByRole('dialog', { name: 'knowledge.quickSwitcher' })).toBeNull()
    invoker.remove()
  })
})

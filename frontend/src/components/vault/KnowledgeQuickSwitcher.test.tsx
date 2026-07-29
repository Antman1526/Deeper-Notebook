import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  requestCommandSurface,
  resetCommandSurfaceStore,
} from '@/lib/commands/command-surface-store'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'

const catalog = vi.hoisted(() => ({
  candidates: [
    {
      key: 'vault:fixture\\0note:evidence',
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

vi.mock('@/lib/hooks/use-knowledge-command-data', () => ({
  useKnowledgeCatalog: () => catalog,
}))

import { KnowledgeQuickSwitcher } from './KnowledgeQuickSwitcher'

describe('KnowledgeQuickSwitcher', () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollIntoView = vi.fn()
    resetCommandSurfaceStore()
    useKnowledgeWorkspaceStore.getState().resetWorkspace()
    catalog.isLoading = false
    catalog.failedVaultCount = 0
    catalog.retryFailedVaults.mockClear()
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
    expect(within(dialog).getByText('knowledge.partialCatalogFailure')).toBeInTheDocument()
    expect(within(dialog).getByRole('option', { name: /Evidence/ })).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.retry' }))
    await waitFor(() => expect(catalog.retryFailedVaults).toHaveBeenCalledOnce())
  })
})

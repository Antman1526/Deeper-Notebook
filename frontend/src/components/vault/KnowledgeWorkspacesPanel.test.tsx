import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { NamedKnowledgeWorkspaceSummary } from '@/lib/api/knowledge-navigation'
import { KnowledgeWorkspacesPanel } from './KnowledgeWorkspacesPanel'

const researchDesk: NamedKnowledgeWorkspaceSummary = {
  id: 'named_knowledge_workspace:research', name: 'Research desk', revision: 7,
  updatedAt: '2026-07-31T00:00:00.000Z',
}

function renderPanel(overrides: Partial<React.ComponentProps<typeof KnowledgeWorkspacesPanel>> = {}) {
  const props = {
    workspaces: [researchDesk],
    onSaveCurrentAs: vi.fn(async () => undefined),
    onOpen: vi.fn(async () => undefined),
    onRename: vi.fn(async () => undefined),
    onDuplicate: vi.fn(async () => undefined),
    onReplaceWithCurrent: vi.fn(async () => undefined),
    onDelete: vi.fn(async () => undefined),
    onRefresh: vi.fn(async () => undefined),
    ...overrides,
  }
  render(<KnowledgeWorkspacesPanel {...props} />)
  return props
}

describe('KnowledgeWorkspacesPanel', () => {
  it('opens Save Current As from command intent', () => {
    renderPanel({ commandIntent: { id: 1, kind: 'save' } })
    expect(screen.getByRole('form', { name: 'Workspace editor' })).toBeVisible()
  })

  it('opens explicit revision-aware replacement selection from command intent', () => {
    renderPanel({ commandIntent: { id: 1, kind: 'replace' } })
    expect(screen.getByRole('status')).toHaveTextContent('Select a saved workspace')
  })
  it('lists Current Session separately and opens a named workspace at its listed revision', async () => {
    const props = renderPanel()

    expect(screen.getByText('Current Session')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Open Research desk' }))

    await vi.waitFor(() => expect(props.onOpen).toHaveBeenCalledWith(researchDesk))
  })

  it('keeps the editor open after a revision conflict and refreshes the metadata', async () => {
    const props = renderPanel({
      onRename: vi.fn(async () => { throw Object.assign(new Error('conflict'), { response: { status: 409 } }) }),
    })

    fireEvent.click(screen.getByRole('button', { name: 'Rename Research desk' }))
    fireEvent.change(screen.getByLabelText('Workspace name'), { target: { value: 'New research desk' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save rename' }))

    await vi.waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Workspace changed elsewhere'))
    expect(screen.getByLabelText('Workspace name')).toHaveValue('New research desk')
    expect(props.onRefresh).toHaveBeenCalledOnce()
  })
})

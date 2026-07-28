import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const states = vi.hoisted(() => ({ graph: { isLoading: false, isError: false }, links: { isLoading: false, isError: false } }))

vi.mock('@/lib/hooks/use-vault', () => ({
  useVaults: () => ({ data: [{ id: 'vault:one', name: 'Fixture', format_mode: 'markdown', state: 'ready-read-only', watch_enabled: true }], isLoading: false, isError: false }),
  useVaultFiles: () => ({ data: [{ id: 'vault_file:one', note_id: 'note:derived-projection-id', vault_id: 'vault:one', relative_path: 'notes/one.md', file_kind: 'markdown', format: 'markdown', content_hash: null, parse_status: 'parsed' }], isLoading: false, isError: false }),
  useVaultPage: () => ({ data: { note: { id: 'note:derived-projection-id', title: 'One', properties: {}, tags: [] }, blocks: [], tasks: [], outgoing_links: [], backlinks: [] }, isLoading: false, isError: false }),
  useVaultBacklinks: () => ({ data: [], ...states.links }),
  useVaultOutgoing: () => ({ data: [], ...states.links }),
  useVaultGraph: () => ({ data: { nodes: [], edges: [] }, ...states.graph }),
  useScanVault: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock('./VaultGraph', () => ({ VaultGraph: () => <div /> }))
vi.mock('./VaultLinks', () => ({ VaultLinks: () => <div /> }))
vi.mock('./VaultMarkdown', () => ({ VaultMarkdown: () => <div /> }))

import { KnowledgeExplorer } from './KnowledgeExplorer'

async function selectNote() {
  render(<KnowledgeExplorer />)
  await waitFor(() => expect(screen.getByRole('treeitem')).toBeInTheDocument())
  fireEvent.click(screen.getByRole('treeitem', { name: 'notes/one.md' }))
}

describe('KnowledgeExplorer query states', () => {
  it('shows loading state for link and graph queries instead of empty panes', async () => {
    states.links = { isLoading: true, isError: false }
    states.graph = { isLoading: true, isError: false }
    await selectNote()
    expect(screen.getByText('knowledge.linksLoading')).toBeInTheDocument()
    expect(screen.getByText('knowledge.noProperties')).toBeInTheDocument()
    const graphTab = screen.getByRole('tab', { name: 'knowledge.localGraph' })
    graphTab.focus()
    fireEvent.keyDown(graphTab, { key: 'Enter' })
    await waitFor(() => expect(screen.getByText('knowledge.graphLoading')).toBeInTheDocument())
  })

  it('shows errors for link and graph queries instead of empty panes', async () => {
    states.links = { isLoading: false, isError: true }
    states.graph = { isLoading: false, isError: true }
    await selectNote()
    expect(screen.getByText('knowledge.linksLoadError')).toBeInTheDocument()
    const graphTab = screen.getByRole('tab', { name: 'knowledge.localGraph' })
    graphTab.focus()
    fireEvent.keyDown(graphTab, { key: 'Enter' })
    await waitFor(() => expect(screen.getByText('knowledge.graphLoadError')).toBeInTheDocument())
  })
})

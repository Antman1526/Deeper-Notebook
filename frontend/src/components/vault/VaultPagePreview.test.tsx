import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  VaultPageContractError,
  vaultApi,
  type VaultLink,
  type VaultPage,
} from '@/lib/api/vault'

vi.mock('@/lib/api/vault', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/vault')>()
  return {
    ...actual,
    vaultApi: {
      ...actual.vaultApi,
      page: vi.fn(),
    },
  }
})

import { VaultPagePreview } from './VaultPagePreview'

const resolvedLinkFixture = {
  id: 'link:research',
  source_note_id: 'note:plan',
  target_note_id: 'note:research',
  target_note_title: 'Research',
  target_relative_path: 'pages/research.md',
  target_text: 'Research',
  link_kind: 'wikilink',
  resolved: true,
  source_start: 0,
  source_end: 12,
} satisfies VaultLink

const pageFixture = {
  file: {
    id: 'file:research',
    note_id: 'note:research',
    vault_id: 'vault:one',
    relative_path: 'pages/research.md',
    file_kind: 'markdown',
    format: 'markdown',
    content_hash: 'a'.repeat(64),
    parse_status: 'parsed',
    size_bytes: 42,
    modified_ns: 1,
    encoding: 'utf-8',
    newline: 'lf',
    deleted_state: 'present',
  },
  note: {
    id: 'note:research',
    title: 'Research',
    source_format: 'markdown',
  },
  blocks: [
    { markdown: 'First excerpt' },
    { markdown: '' },
    { markdown: 'Second excerpt' },
    { markdown: 'Third excerpt' },
    { markdown: 'Fourth excerpt' },
  ],
  tasks: [],
  outgoing_links: [resolvedLinkFixture],
  backlinks: [resolvedLinkFixture],
} satisfies VaultPage

function createClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

function previewFixture({
  onNavigate = vi.fn(),
}: {
  onNavigate?: (noteId: string) => void
} = {}) {
  return (
    <VaultPagePreview
      vaultId="vault:one"
      link={resolvedLinkFixture}
      onNavigate={onNavigate}
      trigger={<button type="button">Research</button>}
    />
  )
}

function renderPreview(node = previewFixture(), client = createClient()) {
  return render(
    <QueryClientProvider client={client}>{node}</QueryClientProvider>,
  )
}

async function openPreviewByHover() {
  fireEvent.mouseEnter(screen.getByRole('button', { name: 'Research' }))
  await act(async () => {
    await vi.advanceTimersByTimeAsync(250)
    await vi.advanceTimersByTimeAsync(1)
  })
  await act(async () => {})
}

async function openPreviewByFocus() {
  fireEvent.focus(screen.getByRole('button', { name: 'Research' }))
  await act(async () => {
    await vi.advanceTimersByTimeAsync(250)
    await vi.advanceTimersByTimeAsync(1)
  })
  await act(async () => {})
}

async function closePreviewWithEscape() {
  await act(async () => {
    fireEvent.keyDown(document, { key: 'Escape' })
  })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
}

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('VaultPagePreview', () => {
  it('cancels pending hover intent when the pointer leaves', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockResolvedValueOnce(pageFixture)
    renderPreview()

    const trigger = screen.getByRole('button', { name: 'Research' })
    fireEvent.mouseEnter(trigger)
    fireEvent.mouseLeave(trigger)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(251)
    })

    expect(vaultApi.page).not.toHaveBeenCalled()
  })

  it('cancels pending focus intent when the trigger blurs', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockResolvedValueOnce(pageFixture)
    renderPreview()

    const trigger = screen.getByRole('button', { name: 'Research' })
    fireEvent.focus(trigger)
    fireEvent.blur(trigger)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(251)
    })

    expect(vaultApi.page).not.toHaveBeenCalled()
  })

  it('loads a bounded preview after hover intent and closes with Escape', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockResolvedValueOnce(pageFixture)
    const client = createClient()
    renderPreview(previewFixture(), client)

    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Research' }))
    expect(vaultApi.page).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250)
      await vi.advanceTimersByTimeAsync(1)
    })
    await act(async () => {})

    expect(vaultApi.page).toHaveBeenCalledWith('vault:one', 'note:research')
    expect(client.getQueryData(['vaults', 'vault:one', 'pages', 'note:research']))
      .toEqual(pageFixture)
    await act(async () => {
      await vi.runOnlyPendingTimersAsync()
    })
    expect(screen.getByText('pages/research.md')).toBeInTheDocument()
    expect(screen.queryByText('Fourth excerpt')).not.toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByText('pages/research.md')).not.toBeInTheDocument()
  })

  it('opens the same preview on keyboard focus', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockResolvedValueOnce(pageFixture)
    renderPreview()

    await openPreviewByFocus()
    await act(async () => {
      await vi.runOnlyPendingTimersAsync()
    })

    expect(screen.getByRole('dialog', { name: 'Research preview' }))
      .toBeInTheDocument()
  })

  it('reuses one validated page query inside the stale window', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockResolvedValueOnce(pageFixture)
    renderPreview()

    await openPreviewByHover()
    await closePreviewWithEscape()
    await openPreviewByFocus()

    expect(vaultApi.page).toHaveBeenCalledTimes(1)
  })

  it('keeps navigation available when the preview query fails', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockRejectedValueOnce(new Error('preview unavailable'))
    const onNavigate = vi.fn()
    renderPreview(previewFixture({ onNavigate }))

    await openPreviewByFocus()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Research' }))

    expect(onNavigate).toHaveBeenCalledWith('note:research')
  })

  it('never displays an absolute path returned by a hostile response', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockRejectedValueOnce(
      new VaultPageContractError('canonical-path-unavailable'),
    )
    renderPreview()

    await openPreviewByHover()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    expect(document.body).not.toHaveTextContent('/Users/')
    expect(screen.getByRole('button', { name: 'Research' }))
      .toBeInTheDocument()
  })
})

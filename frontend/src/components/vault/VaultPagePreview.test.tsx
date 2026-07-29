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
  link = resolvedLinkFixture,
  label = 'Research',
}: {
  onNavigate?: (noteId: string) => void
  link?: VaultLink
  label?: string
} = {}) {
  return (
    <VaultPagePreview
      vaultId="vault:one"
      link={link}
      onNavigate={onNavigate}
      trigger={<button type="button">{label}</button>}
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

async function flushQueryNotifications() {
  await act(async () => {
    await vi.runOnlyPendingTimersAsync()
  })
}

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
  vi.mocked(vaultApi.page).mockReset()
})

describe('VaultPagePreview', () => {
  it('does not install Escape listeners for idle preview links', () => {
    const addEventListener = vi.spyOn(document, 'addEventListener')
    renderPreview(
      <>
        {Array.from({ length: 24 }, (_, index) => (
          <span key={index}>
            {previewFixture({
              label: `Research ${index}`,
              link: {
                ...resolvedLinkFixture,
                id: `link:research:${index}`,
                target_note_id: `note:research:${index}`,
              },
            })}
          </span>
        ))}
      </>,
    )

    expect(
      addEventListener.mock.calls.filter(([eventName]) => eventName === 'keydown'),
    ).toHaveLength(0)
    addEventListener.mockRestore()
  })

  it('cancels pending intent with Escape before a query begins', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockResolvedValueOnce(pageFixture)
    renderPreview()

    const trigger = screen.getByRole('button', { name: 'Research' })
    fireEvent.mouseEnter(trigger)
    fireEvent.keyDown(document, { key: 'Escape' })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(251)
    })

    expect(vaultApi.page).not.toHaveBeenCalled()
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })

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

  it('keeps focus intent pending when hover leaves the trigger', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockResolvedValueOnce(pageFixture)
    renderPreview()

    const trigger = screen.getByRole('button', { name: 'Research' })
    fireEvent.focus(trigger)
    fireEvent.mouseEnter(trigger)
    fireEvent.mouseLeave(trigger)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(251)
    })

    expect(vaultApi.page).toHaveBeenCalledTimes(1)
  })

  it('keeps hover intent pending when the trigger loses focus', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockResolvedValueOnce(pageFixture)
    renderPreview()

    const trigger = screen.getByRole('button', { name: 'Research' })
    fireEvent.mouseEnter(trigger)
    fireEvent.focus(trigger)
    fireEvent.blur(trigger)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(251)
    })

    expect(vaultApi.page).toHaveBeenCalledTimes(1)
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
    expect(onNavigate).toHaveBeenCalledTimes(1)
  })

  it('resets a failed preview and retries after deliberate refocus', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page)
      .mockRejectedValueOnce(new Error('preview unavailable'))
      .mockResolvedValueOnce(pageFixture)
    const onNavigate = vi.fn()
    renderPreview(previewFixture({ onNavigate }))
    const trigger = screen.getByRole('button', { name: 'Research' })

    fireEvent.focus(trigger)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(251)
    })
    await flushQueryNotifications()

    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(trigger)
    expect(onNavigate).toHaveBeenCalledTimes(1)

    fireEvent.blur(trigger)
    fireEvent.focus(trigger)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(251)
    })
    await flushQueryNotifications()

    expect(vaultApi.page).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('dialog', { name: 'Research preview' }))
      .toBeInTheDocument()
  })

  it('suppresses a mismatched canonical page response', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockResolvedValueOnce({
      ...pageFixture,
      file: {
        ...pageFixture.file,
        relative_path: 'pages/different.md',
      },
    })
    renderPreview()

    await openPreviewByFocus()
    await flushQueryNotifications()

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText('pages/different.md')).not.toBeInTheDocument()
  })

  it('keeps navigation closed after mismatch data settles out of the observer', async () => {
    vi.useFakeTimers()
    vi.mocked(vaultApi.page).mockResolvedValueOnce({
      ...pageFixture,
      file: {
        ...pageFixture.file,
        relative_path: 'pages/different.md',
      },
    })
    const onNavigate = vi.fn()
    const client = createClient()
    const view = renderPreview(previewFixture({ onNavigate }), client)

    await openPreviewByFocus()
    await flushQueryNotifications()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
    await act(async () => {})
    client.removeQueries({
      queryKey: ['vaults', 'vault:one', 'pages', 'note:research'],
    })
    view.rerender(
      <QueryClientProvider client={client}>
        {previewFixture({ onNavigate })}
      </QueryClientProvider>,
    )
    await act(async () => {})
    fireEvent.click(screen.getByRole('button', { name: 'Research' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('resets a latched mismatch only when the link identity changes', async () => {
    vi.useFakeTimers()
    const nextLink = {
      ...resolvedLinkFixture,
      id: 'link:next',
      target_note_id: 'note:next',
      target_note_title: 'Next',
      target_relative_path: 'pages/next.md',
      target_text: 'Next',
    } satisfies VaultLink
    const nextPage = {
      ...pageFixture,
      file: {
        ...pageFixture.file,
        id: 'file:next',
        note_id: 'note:next',
        relative_path: 'pages/next.md',
      },
      note: {
        ...pageFixture.note,
        id: 'note:next',
        title: 'Next',
      },
    } satisfies VaultPage
    vi.mocked(vaultApi.page)
      .mockResolvedValueOnce({
        ...pageFixture,
        file: {
          ...pageFixture.file,
          relative_path: 'pages/different.md',
        },
      })
      .mockResolvedValueOnce(nextPage)
    const onNavigate = vi.fn()
    const client = createClient()
    const view = renderPreview(previewFixture({ onNavigate }), client)

    await openPreviewByFocus()
    await flushQueryNotifications()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })

    view.rerender(
      <QueryClientProvider client={client}>
        {previewFixture({
          label: 'Next',
          link: nextLink,
          onNavigate,
        })}
      </QueryClientProvider>,
    )
    const nextTrigger = screen.getByRole('button', { name: 'Next' })
    fireEvent.blur(nextTrigger)
    fireEvent.mouseEnter(nextTrigger)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(251)
    })
    await flushQueryNotifications()

    expect(vaultApi.page).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('dialog', { name: 'Next preview' }))
      .toBeInTheDocument()
    fireEvent.click(nextTrigger)
    expect(onNavigate).toHaveBeenCalledTimes(1)
    expect(onNavigate).toHaveBeenCalledWith('note:next')
  })

  it('reads only enough blocks to build three non-empty excerpts', async () => {
    vi.useFakeTimers()
    let markdownReads = 0
    const blocks = Array.from({ length: 1_000 }, (_, index) => ({
      get markdown() {
        markdownReads += 1
        return `Excerpt ${index}`
      },
    }))
    vi.mocked(vaultApi.page).mockResolvedValueOnce({
      ...pageFixture,
      blocks,
    })
    renderPreview()

    await openPreviewByFocus()
    await flushQueryNotifications()

    expect(markdownReads).toBe(3)
    expect(screen.getByText('Excerpt 2')).toBeInTheDocument()
    expect(screen.queryByText('Excerpt 3')).not.toBeInTheDocument()
  })

  it('truncates excerpts at 240 Unicode code points without splitting a surrogate pair', async () => {
    vi.useFakeTimers()
    const expectedExcerpt = `${'a'.repeat(239)}😀`
    vi.mocked(vaultApi.page).mockResolvedValueOnce({
      ...pageFixture,
      blocks: [{ markdown: `${expectedExcerpt}tail` }],
    })
    renderPreview()

    await openPreviewByFocus()
    await flushQueryNotifications()

    expect(screen.getByText(expectedExcerpt)).toBeInTheDocument()
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

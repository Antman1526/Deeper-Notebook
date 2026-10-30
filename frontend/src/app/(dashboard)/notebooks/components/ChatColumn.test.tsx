import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatColumn } from './ChatColumn'

// v0.8.74 — ChatColumn now uses useQuery (suggested starter questions), so it
// must render inside a QueryClientProvider. The query is disabled when there
// are no sources, but the hook still requires a client.
function renderWithClient(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}
import { useNotes } from '@/lib/hooks/use-notes'
import { useNotebookChat } from '@/lib/hooks/useNotebookChat'

// Mock the hooks
vi.mock('@/lib/hooks/use-notes')
vi.mock('@/lib/hooks/useNotebookChat')
vi.mock('@/components/source/ChatPanel', () => ({
  ChatPanel: () => <div data-testid="chat-panel" />
}))

// Type-safe mock factory for useNotes hook
function createNotesMock(overrides: { isLoading?: boolean } = {}) {
  return {
    data: [],
    isLoading: overrides.isLoading ?? false,
  } as unknown as ReturnType<typeof useNotes>
}

// Type-safe mock factory for useNotebookChat hook
function createChatMock() {
  return {
    messages: [],
    isSending: false,
    tokenCount: 0,
    charCount: 0,
    sessions: [],
    currentSessionId: null,
  } as unknown as ReturnType<typeof useNotebookChat>
}

describe('ChatColumn', () => {
  const baseProps = {
    notebookId: 'test-notebook',
    contextSelections: {
      sources: {},
      notes: {}
    },
    sources: [],
  }

  it('shows loading spinner when fetching data', () => {
    vi.mocked(useNotes).mockReturnValue(createNotesMock({ isLoading: true }))
    vi.mocked(useNotebookChat).mockReturnValue(createChatMock())

    renderWithClient(<ChatColumn {...baseProps} sourcesLoading={true} />)

    // Should show loading spinner
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    expect(useNotebookChat).toHaveBeenCalledWith(expect.objectContaining({
      contextCountsEnabled: false,
    }))
  })

  it('renders chat panel when data is loaded', () => {
    vi.mocked(useNotes).mockReturnValue(createNotesMock({ isLoading: false }))
    vi.mocked(useNotebookChat).mockReturnValue(createChatMock())

    renderWithClient(<ChatColumn {...baseProps} sourcesLoading={false} />)

    // Should show chat panel
    expect(screen.getByTestId('chat-panel')).toBeInTheDocument()
    expect(useNotebookChat).toHaveBeenCalledWith(expect.objectContaining({
      contextCountsEnabled: true,
    }))
  })

  it('waits for every loaded source to receive an explicit context mode', () => {
    vi.mocked(useNotes).mockReturnValue(createNotesMock({ isLoading: false }))
    vi.mocked(useNotebookChat).mockReturnValue(createChatMock())

    renderWithClient(
      <ChatColumn
        {...baseProps}
        sourcesLoading={false}
        sources={[{ id: 'source:one', title: 'Source one' } as never]}
      />,
    )

    expect(useNotebookChat).toHaveBeenCalledWith(expect.objectContaining({
      contextCountsEnabled: false,
    }))
  })
})

// v0.8.130 — starter questions are for an EMPTY chat. They used to be fetched as
// soon as sources arrived, before the saved session had loaded, so whether a chat
// with history fired the request depended on which response came back first.
// Now the fetch waits until the chat history is known.
vi.mock('@/lib/api/notebooks', () => ({
  notebooksApi: { suggestedQuestions: vi.fn(async () => ['What changed?']) },
}))

describe('ChatColumn starter questions', () => {
  const props = {
    notebookId: 'test-notebook',
    contextSelections: { sources: { 'source:1': 'full' as const }, notes: {} },
    sources: [{ id: 'source:1', title: 'One' }] as unknown as Parameters<typeof ChatColumn>[0]['sources'],
    sourcesLoading: false,
  }
  const chatMock = (overrides: Record<string, unknown>) =>
    ({ ...createChatMock(), ...overrides }) as unknown as ReturnType<typeof useNotebookChat>

  it('waits for the chat history before fetching them', async () => {
    const { notebooksApi } = await import('@/lib/api/notebooks')
    vi.mocked(notebooksApi.suggestedQuestions).mockClear()
    vi.mocked(useNotes).mockReturnValue(createNotesMock())
    vi.mocked(useNotebookChat).mockReturnValue(chatMock({ historyLoaded: false }))

    renderWithClient(<ChatColumn {...props} />)
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(notebooksApi.suggestedQuestions).not.toHaveBeenCalled()
  })

  it('does not fetch them when the saved session already has messages', async () => {
    const { notebooksApi } = await import('@/lib/api/notebooks')
    vi.mocked(notebooksApi.suggestedQuestions).mockClear()
    vi.mocked(useNotes).mockReturnValue(createNotesMock())
    vi.mocked(useNotebookChat).mockReturnValue(chatMock({
      historyLoaded: true,
      currentSession: { id: 's1', messages: [{ id: 'm1', type: 'human', content: 'Hi' }] },
    }))

    renderWithClient(<ChatColumn {...props} />)
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(notebooksApi.suggestedQuestions).not.toHaveBeenCalled()
  })

  it('fetches them once for an empty chat', async () => {
    const { notebooksApi } = await import('@/lib/api/notebooks')
    vi.mocked(notebooksApi.suggestedQuestions).mockClear()
    vi.mocked(useNotes).mockReturnValue(createNotesMock())
    vi.mocked(useNotebookChat).mockReturnValue(chatMock({ historyLoaded: true }))

    renderWithClient(<ChatColumn {...props} />)

    await vi.waitFor(() => expect(notebooksApi.suggestedQuestions).toHaveBeenCalledTimes(1))
    expect(notebooksApi.suggestedQuestions).toHaveBeenCalledWith('test-notebook', 4)
  })
})

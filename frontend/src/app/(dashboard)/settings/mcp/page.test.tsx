// v0.8.0 Phase 2 Task 10 — Tests for the MCP Servers settings page.
//
// Mock strategy mirrors page.test files in (dashboard)/:
//   - AppShell stubbed so test doesn't need full layout deps.
//   - next/navigation stubbed (useRouter / usePathname).
//   - All four hook exports stubbed via vi.mock.
//   - useTranslation returns the key as-is (established project pattern).
//   - window.confirm stubbed per test where deletion is exercised.

/* eslint-disable @typescript-eslint/no-explicit-any */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'

// ---- Stub layout shell ----
vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'app-shell' }, children),
}))

// ---- Stub router ----
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/settings/mcp',
}))

// ---- Stub hooks ----
vi.mock('@/lib/hooks/use-mcp-servers', () => ({
  useMCPServers: vi.fn(),
  useCreateMCPServer: vi.fn(),
  useTestMCPServer: vi.fn(),
  useDeleteMCPServer: vi.fn(),
  useUpdateMCPServer: vi.fn(),
}))

// v0.8.41 — RecommendationsPanel has its own dedicated tests; stub it
// out here so the page-level tests don't need a QueryClientProvider
// wrapper just for the panel's useQuery call.
vi.mock('./RecommendationsPanel', () => ({
  RecommendationsPanel: () => React.createElement('div', {
    'data-testid': 'mcp-recommendations-stub',
  }),
}))

import {
  useMCPServers,
  useCreateMCPServer,
  useTestMCPServer,
  useDeleteMCPServer,
  useUpdateMCPServer,
} from '@/lib/hooks/use-mcp-servers'
import MCPServersPage from './page'

// ---- Helpers ----
const makeMutateFn = () => vi.fn()

function mockHooks(overrides: {
  servers?: any[]
  isLoading?: boolean
  createMutate?: ReturnType<typeof vi.fn>
  createIsPending?: boolean
  testMutate?: ReturnType<typeof vi.fn>
  testIsPending?: boolean
  delMutate?: ReturnType<typeof vi.fn>
  delIsPending?: boolean
  updateMutate?: ReturnType<typeof vi.fn>
  updateIsPending?: boolean
} = {}) {
  const {
    servers = [],
    isLoading = false,
    createMutate = makeMutateFn(),
    createIsPending = false,
    testMutate = makeMutateFn(),
    testIsPending = false,
    delMutate = makeMutateFn(),
    delIsPending = false,
    updateMutate = makeMutateFn(),
    updateIsPending = false,
  } = overrides

  vi.mocked(useMCPServers).mockReturnValue({
    data: servers,
    isLoading,
    isError: false,
    error: null,
  } as any)

  vi.mocked(useCreateMCPServer).mockReturnValue({
    mutate: createMutate,
    isPending: createIsPending,
  } as any)

  vi.mocked(useTestMCPServer).mockReturnValue({
    mutate: testMutate,
    isPending: testIsPending,
  } as any)

  vi.mocked(useDeleteMCPServer).mockReturnValue({
    mutate: delMutate,
    isPending: delIsPending,
  } as any)

  vi.mocked(useUpdateMCPServer).mockReturnValue({
    mutate: updateMutate,
    isPending: updateIsPending,
  } as any)

  return { createMutate, testMutate, delMutate, updateMutate }
}

// ---- Tests ----
describe('MCPServersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.restoreAllMocks()
  })

  it('renders the heading and Add button', () => {
    mockHooks()
    render(<MCPServersPage />)

    // t() returns the key as-is (test mock in vitest setup)
    expect(screen.getByText('settings.mcp.title')).toBeInTheDocument()
    expect(screen.getByText('settings.mcp.addButton')).toBeInTheDocument()
  })

  it('Add button is disabled when name is empty', () => {
    mockHooks()
    render(<MCPServersPage />)

    const addBtn = screen.getByText('settings.mcp.addButton')
    expect(addBtn.closest('button')).toBeDisabled()
  })

  it('Add button is disabled when URL is not http(s)', () => {
    mockHooks()
    render(<MCPServersPage />)

    const nameInput = screen.getByPlaceholderText('settings.mcp.namePlaceholder')
    const urlInput = screen.getByPlaceholderText('settings.mcp.urlPlaceholder')

    fireEvent.change(nameInput, { target: { value: 'My Tool' } })
    fireEvent.change(urlInput, { target: { value: 'ftp://bad.com' } })

    const addBtn = screen.getByText('settings.mcp.addButton')
    expect(addBtn.closest('button')).toBeDisabled()
  })

  it('Add button enables and calls create mutation with trimmed name+url', async () => {
    const createMutate = vi.fn()
    mockHooks({ createMutate })
    render(<MCPServersPage />)

    const nameInput = screen.getByPlaceholderText('settings.mcp.namePlaceholder')
    const urlInput = screen.getByPlaceholderText('settings.mcp.urlPlaceholder')

    fireEvent.change(nameInput, { target: { value: '  My Server  ' } })
    fireEvent.change(urlInput, { target: { value: '  https://tool.example.com/mcp  ' } })

    const addBtn = screen.getByText('settings.mcp.addButton')
    expect(addBtn.closest('button')).not.toBeDisabled()

    fireEvent.click(addBtn)

    expect(createMutate).toHaveBeenCalledWith(
      { name: 'My Server', url: 'https://tool.example.com/mcp', enabled: true },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
  })

  it('renders one row per server with Test and Delete buttons', () => {
    mockHooks({
      servers: [
        { id: 'srv:1', name: 'Alpha', url: 'https://alpha.example.com/mcp', enabled: true },
        { id: 'srv:2', name: 'Beta', url: 'https://beta.example.com/mcp', enabled: false },
      ],
    })
    render(<MCPServersPage />)

    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()

    const testBtns = screen.getAllByText('settings.mcp.testButton')
    const delBtns = screen.getAllByText('settings.mcp.deleteButton')
    expect(testBtns).toHaveLength(2)
    expect(delBtns).toHaveLength(2)
  })

  it('renders the current enabled state and an accessible toggle per server', () => {
    mockHooks({
      servers: [
        { id: 'srv:enabled', name: 'Alpha', url: 'https://alpha.example.com/mcp', enabled: true },
        { id: 'srv:disabled', name: 'Beta', url: 'https://beta.example.com/mcp', enabled: false },
      ],
    })
    render(<MCPServersPage />)

    const enabledToggle = screen.getByRole('button', { name: /settings\.mcp\.disableButton Alpha/ })
    const disabledToggle = screen.getByRole('button', { name: /settings\.mcp\.enableButton Beta/ })

    expect(enabledToggle).toHaveAttribute('aria-pressed', 'true')
    expect(disabledToggle).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('settings.mcp.enabledStatus')).toBeInTheDocument()
    expect(screen.getByText('settings.mcp.disabledStatus')).toBeInTheDocument()
  })

  it('toggles enabled with only the existing PATCH enabled payload', () => {
    const updateMutate = vi.fn()
    mockHooks({
      servers: [
        { id: 'srv:1', name: 'Alpha', url: 'https://alpha.example.com/mcp', enabled: true },
      ],
      updateMutate,
    })
    render(<MCPServersPage />)

    fireEvent.click(screen.getByRole('button', { name: /settings\.mcp\.disableButton Alpha/ }))

    expect(updateMutate).toHaveBeenCalledWith(
      { id: 'srv:1', body: { enabled: false } },
      expect.objectContaining({ onSettled: expect.any(Function) }),
    )
    expect(updateMutate.mock.calls[0][0].body).toEqual({ enabled: false })
  })

  it('guards a toggle row against duplicate mutations while the request settles', () => {
    const updateMutate = vi.fn()
    mockHooks({
      servers: [
        { id: 'srv:1', name: 'Alpha', url: 'https://alpha.example.com/mcp', enabled: true },
      ],
      updateMutate,
    })
    render(<MCPServersPage />)

    const toggle = screen.getByRole('button', { name: /settings\.mcp\.disableButton Alpha/ })
    fireEvent.click(toggle)
    fireEvent.click(toggle)

    expect(updateMutate).toHaveBeenCalledTimes(1)
  })

  it('keeps toggle controls isolated from test and delete mutation pending state', () => {
    mockHooks({
      servers: [
        { id: 'srv:1', name: 'Alpha', url: 'https://alpha.example.com/mcp', enabled: true },
      ],
      testIsPending: true,
      delIsPending: true,
    })
    render(<MCPServersPage />)

    expect(screen.getByRole('button', { name: /settings\.mcp\.disableButton Alpha/ })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: 'settings.mcp.testButton' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'settings.mcp.deleteButton' })).toBeDisabled()
  })

  it('uses a stacked responsive row layout with a wrapping control grid', () => {
    mockHooks({
      servers: [
        { id: 'srv:1', name: 'Alpha', url: 'https://alpha.example.com/mcp', enabled: true },
      ],
    })
    render(<MCPServersPage />)

    const row = screen.getByRole('listitem')
    expect(row.className).toContain('flex-col')
    expect(row.className).toContain('sm:flex-row')
    expect(row.querySelector('[data-testid="mcp-server-actions"]')?.className).toContain('grid-cols-2')
  })

  it('clicking Test calls test mutation with server id', () => {
    const testMutate = vi.fn()
    mockHooks({
      servers: [
        { id: 'srv:1', name: 'Alpha', url: 'https://alpha.example.com/mcp', enabled: true },
      ],
      testMutate,
    })
    render(<MCPServersPage />)

    fireEvent.click(screen.getByText('settings.mcp.testButton'))
    expect(testMutate).toHaveBeenCalledWith('srv:1')
  })

  it('shows empty state when server list is empty', () => {
    mockHooks({ servers: [] })
    render(<MCPServersPage />)

    expect(screen.getByText('settings.mcp.empty')).toBeInTheDocument()
  })

  it('shows loading text while fetching', () => {
    mockHooks({ isLoading: true })
    render(<MCPServersPage />)

    expect(screen.getByText('common.loading')).toBeInTheDocument()
  })

  it('delete: window.confirm=true triggers delete mutation with server id', async () => {
    const delMutate = vi.fn()
    mockHooks({
      servers: [
        { id: 'srv:3', name: 'Gamma', url: 'https://gamma.example.com/mcp', enabled: true },
      ],
      delMutate,
    })

    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<MCPServersPage />)

    fireEvent.click(screen.getByText('settings.mcp.deleteButton'))

    await waitFor(() => {
      expect(delMutate).toHaveBeenCalledWith('srv:3')
    })
  })

  it('delete: window.confirm=false does NOT call delete mutation', async () => {
    const delMutate = vi.fn()
    mockHooks({
      servers: [
        { id: 'srv:4', name: 'Delta', url: 'https://delta.example.com/mcp', enabled: true },
      ],
      delMutate,
    })

    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<MCPServersPage />)

    fireEvent.click(screen.getByText('settings.mcp.deleteButton'))

    await waitFor(() => {
      expect(delMutate).not.toHaveBeenCalled()
    })
  })

  // v0.8.1 Item 5 — priority reorder buttons
  it('clicking move-up on middle row calls updateMCPServer with priority below neighbor above', async () => {
    const updateMutate = vi.fn()
    mockHooks({
      servers: [
        { id: 'srv:A', name: 'Alpha', url: 'https://a.example.com/mcp', enabled: true, priority: 90 },
        { id: 'srv:B', name: 'Beta', url: 'https://b.example.com/mcp', enabled: true, priority: 100 },
        { id: 'srv:C', name: 'Gamma', url: 'https://c.example.com/mcp', enabled: true, priority: 110 },
      ],
      updateMutate,
    })
    render(<MCPServersPage />)

    // The move-up buttons are identified by aria-label (t() returns the key).
    const moveUpButtons = screen.getAllByLabelText('settings.mcp.moveUp')
    // Middle row (Beta) is at index 1 of the list — i.e. the second moveUp button.
    fireEvent.click(moveUpButtons[1])

    await waitFor(() => {
      expect(updateMutate).toHaveBeenCalledWith({
        id: 'srv:B',
        body: { priority: 80 }, // Alpha.priority(90) - 10
      })
    })
  })

  it('move-up button disabled on first row; move-down button disabled on last row', () => {
    mockHooks({
      servers: [
        { id: 'srv:X', name: 'First', url: 'https://x.example.com/mcp', enabled: true, priority: 100 },
        { id: 'srv:Y', name: 'Last', url: 'https://y.example.com/mcp', enabled: true, priority: 110 },
      ],
    })
    render(<MCPServersPage />)

    const moveUpButtons = screen.getAllByLabelText('settings.mcp.moveUp')
    const moveDownButtons = screen.getAllByLabelText('settings.mcp.moveDown')

    // First row: move-up disabled
    expect(moveUpButtons[0]).toBeDisabled()
    // First row: move-down NOT disabled
    expect(moveDownButtons[0]).not.toBeDisabled()
    // Last row: move-down disabled
    expect(moveDownButtons[1]).toBeDisabled()
    // Last row: move-up NOT disabled
    expect(moveUpButtons[1]).not.toBeDisabled()
  })
})

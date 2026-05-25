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
}))

import {
  useMCPServers,
  useCreateMCPServer,
  useTestMCPServer,
  useDeleteMCPServer,
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

  return { createMutate, testMutate, delMutate }
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
})

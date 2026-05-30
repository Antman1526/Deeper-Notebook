import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { McpToolPicker } from './McpToolPicker'

// v0.8.42 — tests for the per-conversation MCP tool picker. The
// picker is a controlled component: the parent (`useNotebookChat`)
// owns the `disabled` array and the `onToggle` handler. We mock
// `useMCPServers` since the picker reads it via hooks.

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_k: string, opts?: { defaultValue?: string; [k: string]: unknown }) => {
      if (!opts) return _k
      let s = opts.defaultValue ?? _k
      for (const [k, v] of Object.entries(opts)) {
        if (k === 'defaultValue') continue
        s = s.replace(new RegExp(`{{\\s*${k}\\s*}}`, 'g'), String(v))
      }
      return s
    },
  }),
}))

// Stub Popover/Checkbox/Label so JSDOM renders content unconditionally.
vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', { 'data-testid': 'popover-root' }, children),
  PopoverTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) =>
    asChild ? children : React.createElement('div', null, children),
  PopoverContent: ({ children, ...rest }: { children: React.ReactNode } & Record<string, unknown>) =>
    React.createElement('div', { 'data-testid': rest['data-testid'] }, children),
}))

vi.mock('@/components/ui/checkbox', () => ({
  Checkbox: ({ id, checked, onCheckedChange, ...rest }: {
    id?: string
    checked?: boolean
    onCheckedChange?: (v: boolean) => void
  } & Record<string, unknown>) =>
    React.createElement('input', {
      type: 'checkbox',
      id,
      checked: !!checked,
      onChange: () => onCheckedChange?.(!checked),
      ...rest,
    }),
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children, htmlFor, ...rest }: {
    children: React.ReactNode
    htmlFor?: string
  } & Record<string, unknown>) =>
    React.createElement('label', { htmlFor, ...rest }, children),
}))

const mockServers = vi.fn()
vi.mock('@/lib/hooks/use-mcp-servers', () => ({
  useMCPServers: () => ({ data: mockServers() }),
}))

beforeEach(() => {
  mockServers.mockReset()
})

describe('McpToolPicker', () => {
  it('renders nothing when there are no enabled MCP servers', () => {
    mockServers.mockReturnValue([])
    const { container } = render(
      <McpToolPicker disabled={[]} onToggle={() => {}} />,
    )
    expect(container.textContent).toBe('')
  })

  it('shows N/T tools count in the trigger label', () => {
    mockServers.mockReturnValue([
      { id: '1', name: 'SearXNG', url: 'http://x', enabled: true, priority: 100 },
      { id: '2', name: 'Crawl4AI', url: 'http://y', enabled: true, priority: 100 },
      { id: '3', name: 'Playwright', url: 'http://z', enabled: true, priority: 100 },
    ])
    render(<McpToolPicker disabled={['SearXNG']} onToggle={() => {}} />)
    // 2/3 enabled — SearXNG is disabled, the other two stay.
    expect(screen.getByTestId('mcp-tool-picker-trigger').textContent)
      .toMatch(/2\/3 tools/)
  })

  it('hides registry-disabled servers from the list', () => {
    mockServers.mockReturnValue([
      { id: '1', name: 'SearXNG', url: 'http://x', enabled: true, priority: 100 },
      { id: '2', name: 'DeadServer', url: 'http://d', enabled: false, priority: 100 },
    ])
    render(<McpToolPicker disabled={[]} onToggle={() => {}} />)
    expect(screen.getByText('SearXNG')).toBeInTheDocument()
    expect(screen.queryByText('DeadServer')).not.toBeInTheDocument()
  })

  it('checkbox state reflects the disabled array (case-insensitive match)', () => {
    mockServers.mockReturnValue([
      { id: '1', name: 'SearXNG', url: 'http://x', enabled: true, priority: 100 },
      { id: '2', name: 'Crawl4AI', url: 'http://y', enabled: true, priority: 100 },
    ])
    render(
      <McpToolPicker disabled={['searxng']} onToggle={() => {}} />,
    )
    const searxngCb = screen.getByTestId('mcp-pick-1') as HTMLInputElement
    const crawlCb = screen.getByTestId('mcp-pick-2') as HTMLInputElement
    expect(searxngCb.checked).toBe(false)
    expect(crawlCb.checked).toBe(true)
  })

  it('clicking a checkbox calls onToggle with the server name', () => {
    mockServers.mockReturnValue([
      { id: '1', name: 'SearXNG', url: 'http://x', enabled: true, priority: 100 },
    ])
    const onToggle = vi.fn()
    render(<McpToolPicker disabled={[]} onToggle={onToggle} />)
    const cb = screen.getByTestId('mcp-pick-1')
    fireEvent.click(cb)
    expect(onToggle).toHaveBeenCalledWith('SearXNG')
  })
})

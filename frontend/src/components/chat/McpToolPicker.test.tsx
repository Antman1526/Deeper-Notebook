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
const mockWebSearch = vi.fn()
vi.mock('@/lib/hooks/use-mcp-servers', () => ({
  useMCPServers: () => ({ data: mockServers() }),
  useWebSearchStatus: () => ({ data: mockWebSearch() }),
}))

beforeEach(() => {
  mockServers.mockReset()
  mockWebSearch.mockReset()
  // Default: web search not configured (most existing tests assume this).
  mockWebSearch.mockReturnValue(undefined)
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

  // v0.8.65 — built-in web_search tool surfaced as a synthetic row.
  it('renders the web_search row (with provider) when web search is enabled', () => {
    mockServers.mockReturnValue([])
    mockWebSearch.mockReturnValue({ enabled: true, provider: 'serper', tool_name: 'web_search' })
    render(<McpToolPicker disabled={[]} onToggle={() => {}} />)
    expect(screen.getByTestId('mcp-pick-web-search')).toBeInTheDocument()
    expect(screen.getByText(/web search \(serper\)/i)).toBeInTheDocument()
  })

  it('shows the picker even with ZERO MCP servers when web search is enabled', () => {
    mockServers.mockReturnValue([])
    mockWebSearch.mockReturnValue({ enabled: true, provider: 'tavily', tool_name: 'web_search' })
    render(<McpToolPicker disabled={[]} onToggle={() => {}} />)
    // 1/1: just web_search
    expect(screen.getByTestId('mcp-tool-picker-trigger').textContent).toMatch(/1\/1 tools/)
  })

  it('counts web_search alongside MCP servers in the trigger label', () => {
    mockServers.mockReturnValue([
      { id: '1', name: 'Crawl4AI', url: 'http://y', enabled: true, priority: 100 },
    ])
    mockWebSearch.mockReturnValue({ enabled: true, provider: 'serper', tool_name: 'web_search' })
    render(<McpToolPicker disabled={[]} onToggle={() => {}} />)
    // web_search + Crawl4AI both on → 2/2
    expect(screen.getByTestId('mcp-tool-picker-trigger').textContent).toMatch(/2\/2 tools/)
  })

  it('web_search checkbox reflects the disabled array', () => {
    mockServers.mockReturnValue([])
    mockWebSearch.mockReturnValue({ enabled: true, provider: 'serper', tool_name: 'web_search' })
    render(<McpToolPicker disabled={['web_search']} onToggle={() => {}} />)
    const cb = screen.getByTestId('mcp-pick-web-search') as HTMLInputElement
    expect(cb.checked).toBe(false)
  })

  it('clicking web_search calls onToggle("web_search")', () => {
    mockServers.mockReturnValue([])
    mockWebSearch.mockReturnValue({ enabled: true, provider: 'serper', tool_name: 'web_search' })
    const onToggle = vi.fn()
    render(<McpToolPicker disabled={[]} onToggle={onToggle} />)
    fireEvent.click(screen.getByTestId('mcp-pick-web-search'))
    expect(onToggle).toHaveBeenCalledWith('web_search')
  })

  it('hides the web_search row when web search is disabled (no provider)', () => {
    mockServers.mockReturnValue([
      { id: '1', name: 'Crawl4AI', url: 'http://y', enabled: true, priority: 100 },
    ])
    mockWebSearch.mockReturnValue({ enabled: false, provider: null, tool_name: 'web_search' })
    render(<McpToolPicker disabled={[]} onToggle={() => {}} />)
    expect(screen.queryByTestId('mcp-pick-web-search')).not.toBeInTheDocument()
    expect(screen.getByTestId('mcp-tool-picker-trigger').textContent).toMatch(/1\/1 tools/)
  })

  it('shows the tool-calling capability hint when web search is enabled', () => {
    mockServers.mockReturnValue([])
    mockWebSearch.mockReturnValue({ enabled: true, provider: 'serper', tool_name: 'web_search' })
    render(<McpToolPicker disabled={[]} onToggle={() => {}} />)
    expect(screen.getByTestId('mcp-pick-web-search-hint').textContent).toMatch(/tool calling/i)
  })

  it('does NOT show the capability hint when web search is off', () => {
    mockServers.mockReturnValue([
      { id: '1', name: 'Crawl4AI', url: 'http://y', enabled: true, priority: 100 },
    ])
    mockWebSearch.mockReturnValue({ enabled: false, provider: null, tool_name: 'web_search' })
    render(<McpToolPicker disabled={[]} onToggle={() => {}} />)
    expect(screen.queryByTestId('mcp-pick-web-search-hint')).not.toBeInTheDocument()
  })

  // v0.8.82 — keyless scholarly_search surfaced as a second synthetic row so
  // the always-on tool has a per-turn off-switch like web_search does.
  describe('scholarly_search row', () => {
    const bothOn = {
      enabled: true,
      provider: 'wikipedia',
      tool_name: 'web_search',
      scholarly_enabled: true,
      scholarly_tool_name: 'scholarly_search',
    }

    it('renders the scholarly row when scholarly search is enabled', () => {
      mockServers.mockReturnValue([])
      mockWebSearch.mockReturnValue(bothOn)
      render(<McpToolPicker disabled={[]} onToggle={() => {}} />)
      expect(screen.getByTestId('mcp-pick-scholarly-search')).toBeInTheDocument()
      expect(screen.getByText(/scholarly search/i)).toBeInTheDocument()
    })

    it('counts both built-in tools in the trigger label', () => {
      mockServers.mockReturnValue([])
      mockWebSearch.mockReturnValue(bothOn)
      render(<McpToolPicker disabled={[]} onToggle={() => {}} />)
      expect(screen.getByTestId('mcp-tool-picker-trigger').textContent).toMatch(/2\/2 tools/)
    })

    it('scholarly checkbox reflects the disabled array (case-insensitive)', () => {
      mockServers.mockReturnValue([])
      mockWebSearch.mockReturnValue(bothOn)
      render(<McpToolPicker disabled={['Scholarly_Search']} onToggle={() => {}} />)
      const cb = screen.getByTestId('mcp-pick-scholarly-search') as HTMLInputElement
      expect(cb.checked).toBe(false)
      expect(screen.getByTestId('mcp-tool-picker-trigger').textContent).toMatch(/1\/2 tools/)
    })

    it('clicking scholarly calls onToggle("scholarly_search")', () => {
      mockServers.mockReturnValue([])
      mockWebSearch.mockReturnValue(bothOn)
      const onToggle = vi.fn()
      render(<McpToolPicker disabled={[]} onToggle={onToggle} />)
      fireEvent.click(screen.getByTestId('mcp-pick-scholarly-search'))
      expect(onToggle).toHaveBeenCalledWith('scholarly_search')
    })

    it('shows the picker and the capability hint with only scholarly enabled', () => {
      mockServers.mockReturnValue([])
      mockWebSearch.mockReturnValue({
        enabled: false,
        provider: null,
        tool_name: 'web_search',
        scholarly_enabled: true,
        scholarly_tool_name: 'scholarly_search',
      })
      render(<McpToolPicker disabled={[]} onToggle={() => {}} />)
      expect(screen.getByTestId('mcp-pick-scholarly-search')).toBeInTheDocument()
      expect(screen.queryByTestId('mcp-pick-web-search')).not.toBeInTheDocument()
      expect(screen.getByTestId('mcp-tool-picker-trigger').textContent).toMatch(/1\/1 tools/)
      expect(screen.getByTestId('mcp-pick-web-search-hint')).toBeInTheDocument()
    })

    it('hides the scholarly row for a pre-v0.8.82 response shape', () => {
      mockServers.mockReturnValue([])
      mockWebSearch.mockReturnValue({ enabled: true, provider: 'serper', tool_name: 'web_search' })
      render(<McpToolPicker disabled={[]} onToggle={() => {}} />)
      expect(screen.queryByTestId('mcp-pick-scholarly-search')).not.toBeInTheDocument()
      expect(screen.getByTestId('mcp-tool-picker-trigger').textContent).toMatch(/1\/1 tools/)
    })
  })
})

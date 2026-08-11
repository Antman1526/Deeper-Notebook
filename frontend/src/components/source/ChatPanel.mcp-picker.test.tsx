import React from 'react'
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChatPanel } from './ChatPanel'

// JSDOM doesn't implement scrollIntoView; ChatPanel's auto-scroll
// effect calls it on mount. Stub it so the render doesn't throw.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

// v0.8.46 — regression guard for the gap where <McpToolPicker> was
// built + tested (v0.8.42) but never mounted in ChatPanel, leaving
// the whole per-conversation MCP-picker feature unreachable from the
// UI. These tests assert ChatPanel renders the picker when
// `onToggleMcpServer` is supplied and forwards the disable list — and
// omits it entirely otherwise.
//
// ChatPanel has a heavy dependency tree; we stub the children that
// aren't under test so the render stays fast + focused.

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (_k: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _k,
  }),
}))

vi.mock('@/lib/hooks/use-modal-manager', () => ({
  useModalManager: () => ({ openModal: vi.fn() }),
}))

vi.mock('@/lib/hooks/use-evaluation', () => ({
  useLatestMessageEvaluations: () => ({
    data: {},
    isLoading: false,
    isError: false,
  }),
}))

vi.mock('./ModelSelector', () => ({
  ModelSelector: () => <div data-testid="model-selector" />,
}))

vi.mock('@/components/source/SessionManager', () => ({
  SessionManager: () => <div data-testid="session-manager" />,
}))

vi.mock('@/components/source/MessageActions', () => ({
  MessageActions: () => <div data-testid="message-actions" />,
}))

vi.mock('@/components/common/ContextIndicator', () => ({
  ContextIndicator: () => <div data-testid="context-indicator" />,
}))

vi.mock('@/components/chat/CitationPill', () => ({
  CitationPill: () => <span data-testid="citation-pill" />,
}))

vi.mock('@/components/chat/ChatMessageProviderBadge', () => ({
  ChatMessageProviderBadge: () => <span data-testid="provider-badge" />,
}))

vi.mock('@/components/deeper-notebook', () => ({
  RunTimeline: () => <div data-testid="run-timeline" />,
}))

// The component under observation: capture the props it receives so we
// can assert the disable list + toggle handler were forwarded.
const pickerProps = vi.fn()
vi.mock('@/components/chat/McpToolPicker', () => ({
  McpToolPicker: (props: { disabled: string[]; onToggle: (n: string) => void }) => {
    pickerProps(props)
    return <div data-testid="mcp-tool-picker" />
  },
}))

const baseProps = {
  messages: [],
  isStreaming: false,
  contextIndicators: null,
  onSendMessage: vi.fn(),
}

describe('ChatPanel — v0.8.46 MCP picker mount', () => {
  it('renders McpToolPicker when onToggleMcpServer is provided', () => {
    pickerProps.mockClear()
    const onToggle = vi.fn()
    render(
      <ChatPanel
        {...baseProps}
        onModelChange={vi.fn()}
        disabledMcpServers={['SearXNG']}
        onToggleMcpServer={onToggle}
      />,
    )
    expect(screen.getByTestId('mcp-tool-picker')).toBeInTheDocument()
    // Forwarded the current disable list + the toggle handler.
    expect(pickerProps).toHaveBeenCalled()
    const props = pickerProps.mock.calls[0][0]
    expect(props.disabled).toEqual(['SearXNG'])
    expect(props.onToggle).toBe(onToggle)
  })

  it('does NOT render McpToolPicker when onToggleMcpServer is omitted', () => {
    pickerProps.mockClear()
    render(
      <ChatPanel
        {...baseProps}
        onModelChange={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('mcp-tool-picker')).not.toBeInTheDocument()
    expect(pickerProps).not.toHaveBeenCalled()
  })

  it('passes an empty array to the picker when disabledMcpServers is undefined', () => {
    pickerProps.mockClear()
    render(
      <ChatPanel
        {...baseProps}
        onModelChange={vi.fn()}
        onToggleMcpServer={vi.fn()}
      />,
    )
    expect(screen.getByTestId('mcp-tool-picker')).toBeInTheDocument()
    expect(pickerProps.mock.calls[0][0].disabled).toEqual([])
  })
})

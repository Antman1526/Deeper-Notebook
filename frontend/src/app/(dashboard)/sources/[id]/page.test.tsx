import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import SourceDetailPage from './page'

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'source%3Aone' }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('@/components/source/ChatPanel', () => ({
  ChatPanel: () => <div>Source chat</div>,
}))

vi.mock('@/components/source/SourceDetailContent', () => ({
  SourceDetailContent: ({ sourceId }: { sourceId: string }) => <div>Source detail {sourceId}</div>,
}))

vi.mock('@/lib/hooks/use-navigation', () => ({
  useNavigation: () => ({
    getReturnPath: () => '/sources',
    getReturnLabel: () => 'Sources',
    clearReturnTo: vi.fn(),
  }),
}))

vi.mock('@/lib/hooks/useSourceChat', () => ({
  useSourceChat: () => ({
    messages: [],
    isStreaming: false,
    contextIndicators: [],
    sendMessage: vi.fn(),
    currentSession: null,
    pendingModelOverride: null,
    setModelOverride: vi.fn(),
    sessions: [],
    currentSessionId: null,
    createSession: vi.fn(),
    switchSession: vi.fn(),
    updateSession: vi.fn(),
    deleteSession: vi.fn(),
    loadingSessions: false,
    disabledMcpServers: [],
    toggleDisabledMcpServer: vi.fn(),
  }),
}))

describe('SourceDetailPage', () => {
  it('keeps source detail and chat inside a Collect folio frame', () => {
    render(<SourceDetailPage />)

    expect(screen.getByRole('main', { name: 'Source record' })).toBeInTheDocument()
    expect(screen.getByText('Collect')).toBeInTheDocument()
    expect(screen.getByText('Source detail source:one')).toBeInTheDocument()
    expect(screen.getByText('Source chat')).toBeInTheDocument()
  })
})

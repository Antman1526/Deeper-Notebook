import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import SearchPage from './page'

vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams() }))
vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/lib/hooks/use-search', () => ({ useSearch: () => ({ mutate: vi.fn(), isPending: false, data: undefined }) }))
vi.mock('@/lib/hooks/use-ask', () => ({ useAsk: () => ({ isStreaming: false, strategy: '', answers: [], finalAnswer: null, sendAsk: vi.fn() }) }))
vi.mock('@/lib/hooks/use-models', () => ({
  useModelDefaults: () => ({ data: { default_embedding_model: 'embed', default_chat_model: 'chat' }, isLoading: false }),
  useModels: () => ({ data: [] }),
}))
vi.mock('@/lib/hooks/use-modal-manager', () => ({ useModalManager: () => ({ openModal: vi.fn() }) }))
vi.mock('@/components/search/StreamingResponse', () => ({ StreamingResponse: () => <div>Streaming response</div> }))
vi.mock('@/components/search/AdvancedModelsDialog', () => ({ AdvancedModelsDialog: () => null }))
vi.mock('@/components/search/SaveToNotebooksDialog', () => ({ SaveToNotebooksDialog: () => null }))
vi.mock('@/components/common/LoadingSpinner', () => ({ LoadingSpinner: () => <div>Loading</div> }))
vi.mock('@/lib/hooks/use-translation', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

describe('SearchPage', () => {
  it('keeps ask controls inside the Discover folio without auto-running a request', () => {
    render(<SearchPage />)

    expect(screen.getByRole('main', { name: 'Ask & Search' })).toBeInTheDocument()
    expect(screen.getByText('Discover')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'searchPage.askBeta' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'common.accessibility.enterQuestion' })).toBeInTheDocument()
  })
})

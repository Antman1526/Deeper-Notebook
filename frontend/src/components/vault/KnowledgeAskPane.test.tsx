import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { LocalModelsHealthPayload } from '@/lib/hooks/use-local-models'

const ask = vi.hoisted(() => ({ sendAsk: vi.fn(), isStreaming: false }))
const localModelsHealth = vi.hoisted(() => ({
  data: {
    overall: 'healthy',
    models: [{ name: 'local-research-chat', status: 'healthy', detail: null, latency_ms: 1 }],
  } as LocalModelsHealthPayload,
  isLoading: false,
  isError: false,
  error: null as Error | null,
}))

vi.mock('@/lib/hooks/use-ask', () => ({ useAsk: () => ask }))
vi.mock('@/lib/hooks/use-models', () => ({
  useModelDefaults: () => ({ data: { default_chat_model: 'local-research-chat' } }),
}))
vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelsHealth: () => localModelsHealth,
}))

import { KnowledgeAskPane } from './KnowledgeAskPane'

describe('KnowledgeAskPane', () => {
  beforeEach(() => {
    ask.sendAsk.mockReset()
    localModelsHealth.data = {
      overall: 'healthy',
      models: [{ name: 'local-research-chat', status: 'healthy', detail: null, latency_ms: 1 }],
    }
    localModelsHealth.isLoading = false
    localModelsHealth.isError = false
    localModelsHealth.error = null
  })

  it('does not submit local chat work when opened', () => {
    render(<KnowledgeAskPane selectedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(ask.sendAsk).not.toHaveBeenCalled()
    expect(screen.getByText('1 selected document')).toBeInTheDocument()
  })

  it('fails closed instead of sending a selected-source question through global Ask', () => {
    render(<KnowledgeAskPane selectedDocumentIds={['knowledge_engine_document:plan']} />)

    fireEvent.change(screen.getByLabelText('Question for selected knowledge'), {
      target: { value: 'What changed?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ask selected knowledge' }))

    expect(ask.sendAsk).not.toHaveBeenCalled()
    expect(screen.getByText('Scoped Ask is unavailable until selection-aware chat is available.')).toBeInTheDocument()
  })

  it('disables Ask with the returned readiness reason', () => {
    render(<KnowledgeAskPane selectedDocumentIds={[]} readinessReason="Local research model is unavailable" />)

    expect(screen.getByText('Local research model is unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask selected knowledge' })).toBeDisabled()
  })

  it('uses the existing local health detail as the rendered disable reason', () => {
    localModelsHealth.data = {
      overall: 'degraded',
      models: [{ name: 'local-research-chat', status: 'unhealthy', detail: 'Configured local research model is unavailable', latency_ms: null }],
    }

    render(<KnowledgeAskPane selectedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(screen.getByText('Configured local research model is unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask selected knowledge' })).toBeDisabled()
  })

  it('does not treat a healthy embedding model as readiness for the configured chat model', () => {
    localModelsHealth.data = {
      overall: 'degraded',
      models: [
        { name: 'local-research-embeddings', status: 'healthy', detail: null, latency_ms: 1 },
        { name: 'local-research-chat', status: 'unhealthy', detail: 'Configured chat model is unavailable', latency_ms: null },
      ],
    }

    render(<KnowledgeAskPane selectedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(screen.getByText('Configured chat model is unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask selected knowledge' })).toBeDisabled()
  })
})

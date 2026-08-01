import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { LocalModelsHealthPayload } from '@/lib/hooks/use-local-models'

const ask = vi.hoisted(() => ({ sendAsk: vi.fn(), isStreaming: false }))
const modelDefaults = vi.hoisted(() => ({ default_chat_model: 'local-research-chat' as string | null }))
const configuredModels = vi.hoisted(() => ({
  data: [{
    id: 'local-research-chat', name: 'Local research chat', provider: 'openai_compatible',
    type: 'language' as const, credential: 'credential:local-research',
    created: '', updated: '',
  }],
}))
const localModelsHealth = vi.hoisted(() => ({
  data: {
    overall: 'healthy',
    models: [{ name: 'local-research-chat', credential_id: 'credential:local-research', status: 'healthy', detail: null, latency_ms: 1 }],
  } as LocalModelsHealthPayload,
  isLoading: false,
  isError: false,
  error: null as Error | null,
}))
const routePlan = vi.hoisted(() => ({ data: undefined as any, isError: false, isLoading: false }))
const savedSettings = vi.hoisted(() => ({ data: { execution_policy: 'strict_local', compute_profile: 'balanced', role_overrides: {} } as any }))
const routePlanCalls = vi.hoisted(() => [] as unknown[][])

vi.mock('@/lib/hooks/use-ask', () => ({ useAsk: () => ask }))
vi.mock('@/lib/hooks/use-models', () => ({
  useModelDefaults: () => ({ data: modelDefaults }),
  useModels: () => ({ data: configuredModels.data }),
}))
vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelsHealth: () => localModelsHealth,
  useLocalModelSettings: () => savedSettings,
  useModelRoutePlan: (...args: unknown[]) => { routePlanCalls.push(args); return routePlan },
}))

import { KnowledgeAskPane } from './KnowledgeAskPane'

describe('KnowledgeAskPane', () => {
  beforeEach(() => {
    routePlan.data = undefined
    routePlan.isError = false
    routePlan.isLoading = false
    routePlanCalls.length = 0
    savedSettings.data = { execution_policy: 'strict_local', compute_profile: 'balanced', role_overrides: {} }
    ask.sendAsk.mockReset()
    modelDefaults.default_chat_model = 'local-research-chat'
    configuredModels.data = [{
      id: 'local-research-chat', name: 'Local research chat', provider: 'openai_compatible',
      type: 'language', credential: 'credential:local-research', created: '', updated: '',
    }]
    localModelsHealth.data = {
      overall: 'healthy',
      models: [{ name: 'local-research-chat', credential_id: 'credential:local-research', status: 'healthy', detail: null, latency_ms: 1 }],
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

  it('shows the active Research Chat route without executing it', () => {
    routePlan.data = { role: 'research_chat', outcome: 'ready', selected_model_id: 'qwen-local', selected_provider: 'mlx', resource_tier: 'standard', selection_source: 'automatic', route_reason: 'Verified local route.', escalation_model_ids: [], blocked_reason: null, selected_fingerprint: 'fingerprint', selected_measurements: {} }
    render(<KnowledgeAskPane selectedDocumentIds={[]} />)
    expect(screen.getByText('Research Chat route')).toBeInTheDocument()
    expect(screen.getByText('qwen-local')).toBeInTheDocument()
    expect(ask.sendAsk).not.toHaveBeenCalled()
  })

  it('plans Research Chat with saved Local Preferred settings and its explicit override', () => {
    savedSettings.data = { execution_policy: 'local_preferred', compute_profile: 'maximum_quality', role_overrides: { research_chat: 'qwen-override' } }
    render(<KnowledgeAskPane selectedDocumentIds={[]} />)
    expect(routePlanCalls).toContainEqual([{ role: 'research_chat', execution_policy: 'local_preferred', compute_profile: 'maximum_quality', role_override_model_id: 'qwen-override', modalities: ['text'] }])
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
      models: [{ name: 'local-research-chat', credential_id: 'credential:local-research', status: 'unhealthy', detail: 'Configured local research model is unavailable', latency_ms: null }],
    }

    render(<KnowledgeAskPane selectedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(screen.getByText('Configured local research model is unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask selected knowledge' })).toBeDisabled()
  })

  it('does not treat a healthy embedding model as readiness for the configured chat model', () => {
    localModelsHealth.data = {
      overall: 'degraded',
      models: [
        { name: 'local-research-embeddings', credential_id: 'credential:local-embeddings', status: 'healthy', detail: null, latency_ms: 1 },
        { name: 'local-research-chat', credential_id: 'credential:local-research', status: 'unhealthy', detail: 'Configured chat model is unavailable', latency_ms: null },
      ],
    }

    render(<KnowledgeAskPane selectedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(screen.getByText('Configured chat model is unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask selected knowledge' })).toBeDisabled()
  })

  it('joins the default model record to healthy local health by credential ID, not display name', () => {
    modelDefaults.default_chat_model = 'model:chat-default'
    configuredModels.data = [{
      id: 'model:chat-default', name: 'Qwen chat model', provider: 'openai_compatible',
      type: 'language', credential: 'credential:chat-sidecar', created: '', updated: '',
    }]
    localModelsHealth.data = {
      overall: 'healthy',
      models: [{
        name: 'Desktop llama.cpp chat sidecar', credential_id: 'credential:chat-sidecar',
        status: 'healthy', detail: null, latency_ms: 1,
      }],
    }

    render(<KnowledgeAskPane selectedDocumentIds={['knowledge_engine_document:plan']} />)

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask selected knowledge' })).toBeDisabled()
  })
})

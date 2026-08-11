import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import LocalModelsPage from './page'

type QueryState = {
  data?: unknown
  isError?: boolean
  isFetching?: boolean
  isLoading?: boolean
}

const testState = vi.hoisted(() => ({
  api: {
    delete: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
  },
  benchmarkMutation: {
    data: undefined as unknown,
    isPending: false,
    mutate: vi.fn(),
  },
  cancelMutation: {
    data: undefined as unknown,
    isPending: false,
    mutate: vi.fn(),
  },
  health: { data: undefined as unknown, isLoading: false },
  queries: {
    benchmarks: {} as QueryState,
    inventory: {} as QueryState,
    receipts: {} as QueryState,
    readiness: {} as QueryState,
    settings: {} as QueryState,
  },
  queryCalls: [] as Array<{ enabled?: boolean; key: string }>,
  mutationCalls: 0,
  resetMutation: {
    data: undefined as unknown,
    isPending: false,
    mutate: vi.fn(),
  },
  saveSettingsMutation: { data: undefined as unknown, isPending: false, mutate: vi.fn() },
  routePlans: [] as Array<{ data: unknown; isError: boolean; isLoading: boolean }>,
}))

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => React.createElement('main', { 'data-testid': 'app-shell' }, children),
}))

vi.mock('./DownloadPanel', () => ({
  DownloadPanel: () => React.createElement('section', { 'data-testid': 'download-panel' }, 'Downloads'),
}))

vi.mock('@/components/local-models/ModelInventory', () => ({
  ModelInventory: ({ inventory, isError, isLoading }: { inventory?: { available?: boolean; models?: unknown[] }; isError?: boolean; isLoading?: boolean }) => React.createElement(
    'section',
    {
      'data-available': String(inventory?.available),
      'data-error': String(Boolean(isError)),
      'data-loading': String(Boolean(isLoading)),
      'data-models': String(inventory?.models?.length ?? 0),
      'data-testid': 'model-inventory',
    },
    'Inventory',
  ),
}))

vi.mock('@/components/local-models/RoleBenchmarkPanel', () => ({
  RoleBenchmarkPanel: ({ benchmark, isStarting, onBenchmarkAll, routes }: { benchmark?: { job_id: string }; isStarting?: boolean; onBenchmarkAll: () => void; routes?: unknown[] }) => React.createElement(
    'section',
    {
      'data-benchmark': benchmark?.job_id ?? 'none',
      'data-routes': String(routes?.length ?? 0),
      'data-starting': String(Boolean(isStarting)),
      'data-testid': 'role-benchmark-panel',
    },
    React.createElement('button', { disabled: isStarting, onClick: onBenchmarkAll, type: 'button' }, 'Benchmark every role'),
  ),
}))

vi.mock('@/components/local-models/RouteReceiptPanel', () => ({
  RouteReceiptPanel: ({ isError, isLoading, receipts }: { isError: boolean; isLoading: boolean; receipts: unknown[] }) => React.createElement(
    'section',
    {
      'data-error': String(isError),
      'data-loading': String(isLoading),
      'data-receipts': String(receipts.length),
      'data-testid': 'route-receipt-panel',
    },
    'Routing receipts',
  ),
}))

vi.mock('@/lib/hooks/use-local-models', () => ({
  useLocalModelsHealth: () => testState.health,
  useModelRoutePlan: () => testState.routePlans.shift() ?? ({ data: undefined, isError: false, isLoading: false }),
}))

vi.mock('@/lib/api/client', () => ({ default: testState.api }))

vi.mock('@tanstack/react-query', () => ({
  // React may render the workspace more than once in development; retain the
  // benchmark/cancel/reset call order for each render pass.
  useMutation: () => [testState.benchmarkMutation, testState.cancelMutation, testState.resetMutation, testState.saveSettingsMutation][testState.mutationCalls++ % 4]!,
  useQuery: (options: { enabled?: boolean; queryKey: [string, string] }) => {
    const key = options.queryKey[1]
    testState.queryCalls.push({ enabled: options.enabled, key })
    const stateKey = {
      benchmarks: 'benchmarks',
      inventory: 'inventory',
      readiness: 'readiness',
      settings: 'settings',
      'route-receipts': 'receipts',
    }[key] as keyof typeof testState.queries
    return testState.queries[stateKey]
  },
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

function resetState() {
  testState.api.delete.mockReset()
  testState.api.get.mockReset()
  testState.api.post.mockReset()
  testState.benchmarkMutation.data = undefined
  testState.benchmarkMutation.isPending = false
  testState.benchmarkMutation.mutate.mockReset()
  testState.cancelMutation.data = undefined
  testState.cancelMutation.isPending = false
  testState.cancelMutation.mutate.mockReset()
  testState.resetMutation.data = undefined
  testState.resetMutation.isPending = false
  testState.resetMutation.mutate.mockReset()
  testState.saveSettingsMutation.isPending = false
  testState.saveSettingsMutation.mutate.mockReset()
  testState.health = { data: undefined, isLoading: false }
  testState.mutationCalls = 0
  testState.routePlans = []
  testState.queryCalls = []
  testState.queries.inventory = {
    data: {
      available: true,
      model_dir: '/models',
      models: [{ name: 'qwen-local', path: '/models/qwen.gguf', runnable: true, runtime: 'gguf' }],
    },
  }
  testState.queries.settings = { data: { model_dir: '/models', execution_policy: 'strict_local', compute_profile: 'balanced', local_model_memory_limit_bytes: 0, role_overrides: {}, trusted_external_model_roots: [] } }
  testState.queries.readiness = { data: { available: true, models: [{ model_id: 'qwen-local', format: 'gguf', modality: 'text', readiness: 'ready_verified', readiness_reason: 'verified', measured_tier: 'standard', accepted_roles: ['research_chat'], route_eligible: true }] } }
  testState.queries.benchmarks = { data: { benchmarks: [{ job_id: 'benchmark-1', results: [], status: 'completed' }] } }
  testState.queries.receipts = { data: { receipts: [{ outcome: 'selected', role: 'chat', selected_model_id: 'qwen-local' }] } }
}

beforeEach(resetState)

describe('LocalModelsPage', () => {
  it('composes the role workspace from inventory, benchmarks, and local-only receipts', () => {
    render(<LocalModelsPage />)

    expect(screen.getByTestId('app-shell')).toHaveTextContent('Local model roles')
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('heading', { level: 2, name: 'Local model roles' })).toBeInTheDocument()
    expect(screen.getByTestId('model-inventory')).toHaveAttribute('data-models', '1')
    expect(screen.getByTestId('role-benchmark-panel')).toHaveAttribute('data-routes', '0')
    expect(screen.getByTestId('role-benchmark-panel')).toHaveAttribute('data-benchmark', 'benchmark-1')
    expect(screen.getByTestId('route-receipt-panel')).toHaveAttribute('data-receipts', '1')
    expect(screen.getByTestId('download-panel')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Benchmark every role' }))
    expect(testState.benchmarkMutation.mutate).toHaveBeenCalledWith([
      'chat',
      'source_synthesis',
      'coding_research',
      'study_fast',
    ])
  })

  it('keeps inventory and route receipt loading states visible while measurements refresh', () => {
    testState.queries.inventory = { isFetching: true, isLoading: true }
    testState.queries.receipts = { isLoading: true }

    render(<LocalModelsPage />)

    expect(screen.getByText('Refreshing')).toBeInTheDocument()
    expect(screen.getByTestId('model-inventory')).toHaveAttribute('data-loading', 'true')
    expect(screen.getByTestId('route-receipt-panel')).toHaveAttribute('data-loading', 'true')
  })

  it('preserves disabled benchmark controls and isolates routing and inventory failures', () => {
    testState.benchmarkMutation.isPending = true
    testState.queries.inventory = { isError: true }
    testState.queries.readiness = { isError: true }
    testState.queries.receipts = { isError: true }

    render(<LocalModelsPage />)

    expect(screen.getByText('Local readiness is unavailable')).toBeInTheDocument()
    expect(screen.getByTestId('model-inventory')).toHaveAttribute('data-error', 'true')
    expect(screen.getByTestId('route-receipt-panel')).toHaveAttribute('data-error', 'true')
    expect(screen.getByRole('button', { name: 'Benchmark every role' })).toBeDisabled()
    expect(testState.api.get).not.toHaveBeenCalled()
    expect(testState.api.post).not.toHaveBeenCalled()
    expect(testState.api.delete).not.toHaveBeenCalled()
  })

  it('does not enable readiness, benchmark, or receipt queries until an installed model is runnable', () => {
    testState.queries.inventory = {
      data: {
        available: true,
        model_dir: '/models',
        models: [{ name: 'catalog-only', path: '/models/catalog', runnable: false, runtime: 'transformers' }],
      },
    }

    render(<LocalModelsPage />)

    const dependentQueries = testState.queryCalls.filter(call => ['readiness', 'benchmarks', 'route-receipts'].includes(call.key))
    expect(dependentQueries).toHaveLength(3)
    expect(dependentQueries).toEqual(expect.arrayContaining([
      { enabled: false, key: 'readiness' },
      { enabled: false, key: 'benchmarks' },
      { enabled: false, key: 'route-receipts' },
    ]))
    expect(testState.api.get).not.toHaveBeenCalled()
  })

  it('keeps a degraded library visible but blocks automatic routes', () => {
    testState.queries.readiness = { data: { available: true, models: [{ model_id: 'planned', format: 'mlx', modality: 'text', readiness: 'planned', readiness_reason: 'not installed', measured_tier: null, accepted_roles: [], route_eligible: false }] } }
    render(<LocalModelsPage />)
    expect(screen.getByText('planned: 1')).toBeInTheDocument()
    expect(screen.getByText('No verified local route is currently available.')).toBeInTheDocument()
  })

  it('offers the pending cloud fallback only after saved Local Preferred receives an approval-required route', () => {
    testState.queries.settings = { data: { model_dir: '/models', execution_policy: 'local_preferred', compute_profile: 'maximum_quality', local_model_memory_limit_bytes: 0, role_overrides: {}, trusted_external_model_roots: [] } }
    testState.routePlans = [
      { data: { role: 'research_chat', outcome: 'approval_required', selected_model_id: null, selected_provider: null, resource_tier: null, selection_source: null, route_reason: 'cloud approval required', escalation_model_ids: [], blocked_reason: null, selected_fingerprint: null, selected_measurements: {} }, isError: false, isLoading: false },
      { data: undefined, isError: false, isLoading: false },
    ]
    render(<LocalModelsPage />)
    expect(screen.getByRole('button', { name: 'Review pending cloud fallback' })).toBeInTheDocument()
  })
})

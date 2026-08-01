import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  cancelBenchmark,
  getBenchmarkJobs,
  getLocalModelInventory,
  getRoleRouting,
  getRouteReceipts,
  resetBenchmarks,
  startBenchmark,
  type BenchmarkJob,
  type BenchmarkListResponse,
  type InventoryResponse,
  type RoleRoutingResponse,
  type RouteReceiptResponse,
} from '@/lib/api/local-models'
import apiClient from '@/lib/api/client'

export interface LocalModelHealth {
  name: string
  credential_id?: string | null
  status: 'healthy' | 'unhealthy' | 'not_configured' | 'unknown'
  detail: string | null
  latency_ms: number | null
  runtime?: string | null
  endpoint?: string | null
  probe_path?: string | null
}

export interface LocalModelsHealthPayload {
  overall: 'healthy' | 'degraded' | 'down'
  models: LocalModelHealth[]
}

export function useLocalModelsHealth() {
  return useQuery<LocalModelsHealthPayload>({
    queryKey: ['local-models', 'health'],
    queryFn: async () => (await apiClient.get('/local-models/health')).data,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    retry: 1,
  })
}

export function useLocalModelInventory() {
  return useQuery<InventoryResponse>({
    queryKey: ['local-models', 'inventory'],
    queryFn: getLocalModelInventory,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  })
}

export function useLocalModelRoleRouting(enabled = true) {
  return useQuery<RoleRoutingResponse>({
    queryKey: ['local-models', 'role-routing'],
    queryFn: getRoleRouting,
    enabled,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  })
}

export function useLocalModelBenchmarks(enabled = true) {
  return useQuery<BenchmarkListResponse>({
    queryKey: ['local-models', 'benchmarks'],
    queryFn: getBenchmarkJobs,
    enabled,
    refetchInterval: query => query.state.data?.benchmarks.some(job =>
      job.status === 'queued' || job.status === 'running',
    ) ? 1_500 : false,
  })
}

export function useStartLocalBenchmark() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (roles?: string[]) => startBenchmark(roles),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['local-models', 'benchmarks'] })
      void queryClient.invalidateQueries({ queryKey: ['local-models', 'role-routing'] })
    },
  })
}

export function useCancelLocalBenchmark() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) => cancelBenchmark(jobId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['local-models', 'benchmarks'] }),
  })
}

export function useResetLocalBenchmarks() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: resetBenchmarks,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['local-models', 'benchmarks'] }),
  })
}

export function useLocalModelRouteReceipts(enabled = true) {
  return useQuery<RouteReceiptResponse>({
    queryKey: ['local-models', 'route-receipts'],
    queryFn: getRouteReceipts,
    enabled,
    staleTime: 10_000,
  })
}

export type { BenchmarkJob }

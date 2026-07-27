import apiClient from './client'
import { ObservabilityResponse, SettingsResponse } from '@/lib/types/api'

export const settingsApi = {
  get: async () => {
    const response = await apiClient.get<SettingsResponse>('/settings')
    return response.data
  },

  update: async (data: Partial<SettingsResponse>) => {
    const response = await apiClient.put<SettingsResponse>('/settings', data)
    return response.data
  },

  // v0.7.136 — Read-only observability snapshot. Backend endpoint
  // GET /settings/observability landed in v0.7.130; this client
  // surface closes the loop so operators can see their effective
  // DEEPER_NOTEBOOK_* config from inside the UI. UIs should refetch on demand
  // (no aggressive caching) — operators can change .env between
  // requests, and a stale display would mislead them.
  getObservability: async () => {
    const response = await apiClient.get<ObservabilityResponse>(
      '/settings/observability',
    )
    return response.data
  },
}
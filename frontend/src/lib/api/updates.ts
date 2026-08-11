// v0.8.70 — in-app update notifier API client.
// Server-side check (api/routers/updates.py) avoids CORS and keeps the
// privacy gate enforceable. apiClient.baseURL already ends in `/api`.
import { apiClient } from './client'

export type UpdateVerification = 'verified' | 'unverified' | 'unknown'

export interface UpdateStatus {
  current: string
  latest: string | null
  update_available: boolean
  /** A candidate is actionable only when its release metadata is verified. */
  verification: UpdateVerification
  /** Public GitHub release page; never a package download URL. */
  release_url: string | null
  /** True when an update exists but the user chose to skip that version. */
  skipped: boolean
  skipped_version: string | null
  html_url: string | null
  published_at: string | null
  enabled: boolean
  last_check: string | null
}

export const updatesApi = {
  check: async (force = false): Promise<UpdateStatus> => {
    const { data } = await apiClient.get<UpdateStatus>('/updates/check', {
      params: force ? { force: true } : undefined,
    })
    return data
  },
  skip: async (version: string): Promise<UpdateStatus> => {
    const { data } = await apiClient.post<UpdateStatus>('/updates/skip', { version })
    return data
  },
  setEnabled: async (enabled: boolean): Promise<UpdateStatus> => {
    const { data } = await apiClient.put<UpdateStatus>('/updates/settings', { enabled })
    return data
  },
}

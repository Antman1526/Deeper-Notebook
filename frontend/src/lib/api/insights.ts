import apiClient from './client'

export interface SourceInsightResponse {
  id: string
  source_id: string
  insight_type: string
  content: string
  created: string
  updated: string
}

export interface CreateSourceInsightRequest {
  transformation_id: string
}

export interface InsightCreationResponse {
  status: 'pending'
  message: string
  source_id: string
  transformation_id: string
  command_id?: string
}

export interface CommandJobStatusResponse {
  job_id: string
  status: string
  result?: Record<string, unknown>
  error_message?: string
}

export const insightsApi = {
  listForSource: async (sourceId: string) => {
    const response = await apiClient.get<SourceInsightResponse[]>(`/sources/${sourceId}/insights`)
    return response.data
  },

  get: async (insightId: string) => {
    const response = await apiClient.get<SourceInsightResponse>(`/insights/${insightId}`)
    return response.data
  },

  create: async (sourceId: string, data: CreateSourceInsightRequest) => {
    const response = await apiClient.post<InsightCreationResponse>(
      `/sources/${sourceId}/insights`,
      data
    )
    return response.data
  },

  delete: async (insightId: string) => {
    await apiClient.delete(`/insights/${insightId}`)
  },

  getCommandStatus: async (commandId: string) => {
    const response = await apiClient.get<CommandJobStatusResponse>(
      `/commands/jobs/${commandId}`
    )
    return response.data
  },

  /**
   * Poll command status until completed or failed.
   * Returns true if completed successfully, false if failed or aborted.
   *
   * v0.7.80 — added optional AbortSignal so callers (e.g. SourceDetailContent)
   * can cancel the polling loop on unmount. Previously the loop ran for up
   * to 4 minutes (120 attempts × 2 s) after the component unmounted,
   * hammering /commands/jobs/{id} for a result nobody would consume and
   * triggering downstream invalidateQueries on dead React subtrees.
   * Aborted polls resolve to `false` (same code path as a failed command)
   * so the caller's `.then(success => …)` doesn't run cache invalidation.
   */
  waitForCommand: async (
    commandId: string,
    options?: {
      maxAttempts?: number
      intervalMs?: number
      signal?: AbortSignal
    }
  ): Promise<boolean> => {
    const maxAttempts = options?.maxAttempts ?? 60 // Default 60 attempts
    const intervalMs = options?.intervalMs ?? 2000 // Default 2 seconds
    const signal = options?.signal

    // Sleep helper that resolves early (with a marker) on abort. Avoids
    // burning the full intervalMs after the user has navigated away.
    const abortableSleep = (ms: number): Promise<'timer' | 'abort'> =>
      new Promise(resolve => {
        if (signal?.aborted) {
          resolve('abort')
          return
        }
        const t = setTimeout(() => {
          signal?.removeEventListener('abort', onAbort)
          resolve('timer')
        }, ms)
        const onAbort = () => {
          clearTimeout(t)
          resolve('abort')
        }
        signal?.addEventListener('abort', onAbort, { once: true })
      })

    for (let i = 0; i < maxAttempts; i++) {
      if (signal?.aborted) return false
      try {
        const status = await insightsApi.getCommandStatus(commandId)
        if (signal?.aborted) return false
        if (status.status === 'completed') {
          return true
        }
        if (status.status === 'failed' || status.status === 'canceled') {
          console.error('Command failed:', status.error_message)
          return false
        }
        // Still running, wait and retry
        if ((await abortableSleep(intervalMs)) === 'abort') return false
      } catch (error) {
        if (signal?.aborted) return false
        console.error('Error checking command status:', error)
        // Continue polling on error
        if ((await abortableSleep(intervalMs)) === 'abort') return false
      }
    }
    // Timeout
    console.warn('Command polling timed out')
    return false
  }
}
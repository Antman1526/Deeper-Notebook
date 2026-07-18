import apiClient from './client'

export type CaptureState = 'pending' | 'ready' | 'importing' | 'imported' | 'duplicate' | 'ignored' | 'failed'

export interface CaptureRoot { path: string }
export interface CaptureItem {
  id: string | null
  root_path: string
  relative_path: string
  filename: string
  extension: string
  state: CaptureState
  sha256: string | null
  byte_size: number | null
  modified_ns: number | null
  reason: string | null
}

export interface CaptureNotebookSuggestion {
  id: string
  name: string
  score: number
  reason: string
}

export interface CaptureRoutePreview {
  state: 'ready' | 'no_model' | 'unavailable'
  transcript: string | null
  notebook_suggestions: CaptureNotebookSuggestion[]
  approval_required: true
  reason: string | null
}

export const captureApi = {
  roots: async () => (await apiClient.get<CaptureRoot[]>('/capture/roots')).data,
  addRoot: async (path: string) => (await apiClient.post<CaptureRoot>('/capture/roots', { path })).data,
  items: async () => (await apiClient.get<CaptureItem[]>('/capture/items')).data,
  scan: async (rootPath?: string) => (await apiClient.post<{ items: CaptureItem[] }>('/capture/scan', rootPath ? { root_path: rootPath } : {})).data,
  route: async (path: string) => (await apiClient.post<CaptureRoutePreview>('/capture/route', { path })).data,
}

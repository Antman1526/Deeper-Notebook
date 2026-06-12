import apiClient from './client'
import {
  NotebookResponse,
  CreateNotebookRequest,
  UpdateNotebookRequest,
  NotebookDeletePreview,
  NotebookDeleteResponse,
  NotebookImportPreviewRequest,
  NotebookImportPreviewResponse,
  NotebookImportRequest,
  NotebookImportResponse,
  NotebookVectorizeRequest,
  NotebookVectorizeResponse,
} from '@/lib/types/api'

export const notebooksApi = {
  list: async (params?: { archived?: boolean; order_by?: string }) => {
    const response = await apiClient.get<NotebookResponse[]>('/notebooks', { params })
    return response.data
  },

  get: async (id: string) => {
    const response = await apiClient.get<NotebookResponse>(`/notebooks/${id}`)
    return response.data
  },

  create: async (data: CreateNotebookRequest) => {
    const response = await apiClient.post<NotebookResponse>('/notebooks', data)
    return response.data
  },

  update: async (id: string, data: UpdateNotebookRequest) => {
    const response = await apiClient.put<NotebookResponse>(`/notebooks/${id}`, data)
    return response.data
  },

  deletePreview: async (id: string) => {
    const response = await apiClient.get<NotebookDeletePreview>(
      `/notebooks/${id}/delete-preview`
    )
    return response.data
  },

  delete: async (id: string, deleteExclusiveSources: boolean = false) => {
    const response = await apiClient.delete<NotebookDeleteResponse>(`/notebooks/${id}`, {
      params: { delete_exclusive_sources: deleteExclusiveSources },
    })
    return response.data
  },

  addSource: async (notebookId: string, sourceId: string) => {
    const response = await apiClient.post(`/notebooks/${notebookId}/sources/${sourceId}`)
    return response.data
  },

  removeSource: async (notebookId: string, sourceId: string) => {
    const response = await apiClient.delete(`/notebooks/${notebookId}/sources/${sourceId}`)
    return response.data
  },

  // v0.7.119 — Dry-run an import. Returns the planned notebook name,
  // detected layout, and the notes / sources that would be created.
  // No domain records are touched.
  importPreview: async (data: NotebookImportPreviewRequest) => {
    const response = await apiClient.post<NotebookImportPreviewResponse>(
      '/notebooks/import/preview',
      data,
    )
    return response.data
  },

  // v0.7.119 — Commit the import. Creates a new Notebook + its Notes /
  // Sources, or appends to an existing one.
  importNotebook: async (data: NotebookImportRequest) => {
    const response = await apiClient.post<NotebookImportResponse>(
      '/notebooks/import',
      data,
    )
    return response.data
  },

  // v0.7.119 — Bulk vectorize every Source attached to a notebook.
  // Fire-and-forget: returns immediately with queued command_ids.
  vectorizeSources: async (
    notebookId: string,
    data: NotebookVectorizeRequest = {},
  ) => {
    const response = await apiClient.post<NotebookVectorizeResponse>(
      `/notebooks/${notebookId}/vectorize_sources`,
      data,
    )
    return response.data
  },
}
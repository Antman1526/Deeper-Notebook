// v0.7.105 — Notebook + note export API wrappers. Backend routers live
// in api/routers/exports.py.

import apiClient from './client'
import {
  ExportResponse,
  NotebookExportRequest,
  NoteExportRequest,
} from '@/lib/types/api'

export const exportsApi = {
  exportNotebook: async (notebookId: string, data: NotebookExportRequest) => {
    const response = await apiClient.post<ExportResponse>(
      `/notebooks/${notebookId}/export`,
      data
    )
    return response.data
  },

  exportNote: async (noteId: string, data: NoteExportRequest) => {
    const response = await apiClient.post<ExportResponse>(
      `/notes/${noteId}/export`,
      data
    )
    return response.data
  },
}

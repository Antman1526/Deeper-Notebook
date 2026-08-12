import type { AxiosResponse } from 'axios'

import apiClient from './client'
import {
  ankiHttpOptionsSchema,
  decodeAnkiExportResponse,
  decodeAnkiImportPreview,
  decodeAnkiImportPublish,
  decodeAnkiImportStatus,
  type AnkiHttpOptions,
  type AnkiImportPublish,
  type AnkiImportPreview,
  type AnkiImportStatus,
  type AnkiExportResponse,
} from '@/lib/types/study-anki'

function invalidRequest(): never {
  throw new Error('Invalid Study Anki request')
}

function planId(value: unknown): string {
  if (typeof value !== 'string' || value !== value.trim() || !value || value.length > 512 || /[\u0000-\u001f\u007f]/.test(value)) invalidRequest()
  return value
}

function options(value: unknown): AnkiHttpOptions {
  const parsed = ankiHttpOptionsSchema.safeParse(value ?? { schema_version: 1 })
  if (!parsed.success) invalidRequest()
  return parsed.data
}

function boundedId(value: unknown, maximum: number): string {
  if (typeof value !== 'string' || value !== value.trim() || !value || value.length > maximum || /[\u0000-\u001f\u007f]/.test(value)) invalidRequest()
  return value
}

function importPath(plan: string): string {
  return `/study/plans/${encodeURIComponent(plan)}/anki/import`
}

export const studyAnkiApi = {
  async preview(plan: string, file: File, importOptions?: AnkiHttpOptions, onUploadProgress?: (percent: number) => void): Promise<AnkiImportPreview> {
    if (!(file instanceof File) || !file.name.toLowerCase().endsWith('.apkg')) invalidRequest()
    const form = new FormData()
    form.append('file', file, file.name)
    form.append('options', JSON.stringify(options(importOptions)))
    const response = await apiClient.post(importPath(planId(plan)), form, {
      headers: { 'x-skip-error-toast': '1' },
      onUploadProgress: (event) => {
        if (event.total && onUploadProgress) onUploadProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)))
      },
    })
    return decodeAnkiImportPreview(response.data)
  },

  async status(plan: string, jobId: string): Promise<AnkiImportStatus> {
    const response = await apiClient.get(`${importPath(planId(plan))}/${encodeURIComponent(boundedId(jobId, 128))}`)
    return decodeAnkiImportStatus(response.data)
  },

  async publish(plan: string, jobId: string, requestId: string, importOptions?: AnkiHttpOptions): Promise<AnkiImportPublish> {
    const response = await apiClient.post(`${importPath(planId(plan))}/${encodeURIComponent(boundedId(jobId, 128))}:publish`, {
      upload_id: boundedId(jobId, 128),
      request_id: boundedId(requestId, 256),
      options: options(importOptions),
    })
    return decodeAnkiImportPublish(response.data)
  },

  async export(plan: string, exportOptions?: AnkiHttpOptions): Promise<AnkiExportResponse> {
    const response = await apiClient.post(`/study/plans/${encodeURIComponent(planId(plan))}/anki/export`, {
      schema_version: 1,
      options: options(exportOptions),
    })
    return decodeAnkiExportResponse(response.data)
  },

  async download(downloadId: string): Promise<AxiosResponse<Blob>> {
    const id = boundedId(downloadId, 128)
    if (!/^anki_download:[a-f0-9]{32,64}$/.test(id)) invalidRequest()
    const response = await apiClient.get(`/study/plans/anki/download/${encodeURIComponent(id)}`, { responseType: 'blob' })
    if (!(response.data instanceof Blob) || response.data.size > 128 * 1024 * 1024 || response.data.type !== 'application/zip') throw new Error('Invalid Study Anki response')
    return response
  },
}

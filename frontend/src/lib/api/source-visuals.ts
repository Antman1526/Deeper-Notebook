import apiClient from './client'
import { sourceVisualJobSchema, type SourceVisualJob } from '@/lib/types/source-visuals'

function visualPath(sourceId: string): string {
  return `/sources/${encodeURIComponent(sourceId)}/visual`
}

export const sourceVisualsApi = {
  refresh: async (sourceId: string, requestId: string): Promise<SourceVisualJob> => {
    const response = await apiClient.post(`${visualPath(sourceId)}:refresh`, { request_id: requestId })
    return sourceVisualJobSchema.parse(response.data)
  },

  remove: async (sourceId: string, requestId: string): Promise<SourceVisualJob> => {
    const response = await apiClient.delete(visualPath(sourceId), { data: { request_id: requestId } })
    return sourceVisualJobSchema.parse(response.data)
  },
}

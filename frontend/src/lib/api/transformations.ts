import apiClient from './client'
import {
  Transformation,
  CreateTransformationRequest,
  UpdateTransformationRequest,
  ExecuteTransformationRequest,
  ExecuteTransformationResponse,
  DefaultPrompt
} from '@/lib/types/transformations'

export const transformationsApi = {
  // v0.8.68 — SkillOpt prompt optimization (microsoft/SkillOpt, MIT).
  optimizePrompt: async (
    transformationId: string,
    payload: { source_ids: string[]; criteria: string; epochs?: number },
  ) => {
    const response = await apiClient.post<{ job_id: string; message: string }>(
      `/transformations/${transformationId}/optimize`,
      payload,
    )
    return response.data
  },

  getOptimizeJob: async (jobId: string) => {
    const response = await apiClient.get<{
      status?: string
      result?: {
        original_prompt?: string
        optimized_prompt?: string
        changed?: boolean
      } | null
      error_message?: string | null
    }>(`/commands/jobs/${jobId}`)
    return response.data
  },

  list: async () => {
    const response = await apiClient.get<Transformation[]>('/transformations')
    return response.data
  },

  get: async (id: string) => {
    const response = await apiClient.get<Transformation>(`/transformations/${id}`)
    return response.data
  },

  create: async (data: CreateTransformationRequest) => {
    const response = await apiClient.post<Transformation>('/transformations', data)
    return response.data
  },

  update: async (id: string, data: UpdateTransformationRequest) => {
    const response = await apiClient.put<Transformation>(`/transformations/${id}`, data)
    return response.data
  },

  delete: async (id: string) => {
    await apiClient.delete(`/transformations/${id}`)
  },

  execute: async (data: ExecuteTransformationRequest) => {
    const response = await apiClient.post<ExecuteTransformationResponse>('/transformations/execute', data)
    return response.data
  },

  getDefaultPrompt: async () => {
    const response = await apiClient.get<DefaultPrompt>('/transformations/default-prompt')
    return response.data
  },

  updateDefaultPrompt: async (prompt: { transformation_instructions: string }) => {
    const response = await apiClient.put<DefaultPrompt>('/transformations/default-prompt', prompt)
    return response.data
  }
}
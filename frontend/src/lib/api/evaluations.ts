import apiClient from './client'

export type EvidenceStatus = 'supported' | 'partial' | 'contradicted' | 'unsupported' | 'uncited'

export interface EvidenceSpan {
  source_id: string
  source_content_sha256: string
  source_state: 'current' | 'source_changed'
  start: number
  end: number
  quote: string
}

export interface ClaimVerdict {
  claim: string
  status: EvidenceStatus
  confidence: number
  citation_markers: string[]
  evidence: EvidenceSpan[]
  explanation: string
}

export interface EvaluationDetail {
  run: {
    id: string
    notebook_id: string
    artifact_id?: string | null
    message_id?: string | null
    evaluator_version: string
    model_id?: string | null
    metrics: Record<string, unknown>
    error?: string | null
    created?: string | null
  }
  status: 'pending' | 'running' | 'completed' | 'failed'
  counts: Record<EvidenceStatus, number>
  verdicts: ClaimVerdict[]
}

export interface EvaluationRecheckRequest {
  evaluation_run_id: string
  notebook_id: string
  response_text: string
  sources: Array<{ marker: string; source_id: string }>
}

export const evaluationsApi = {
  get: async (runId: string, notebookId: string): Promise<EvaluationDetail> => {
    const response = await apiClient.get<EvaluationDetail>(
      `/evaluations/${encodeURIComponent(runId)}`,
      { params: { notebook_id: notebookId }, headers: { 'x-skip-error-toast': '1' } },
    )
    return response.data
  },
  recheck: async (payload: EvaluationRecheckRequest): Promise<EvaluationDetail> => {
    const response = await apiClient.post<EvaluationDetail>('/evaluations/recheck', payload)
    return response.data
  },
}

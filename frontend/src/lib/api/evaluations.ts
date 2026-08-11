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

export interface EvaluationSelector {
  artifactId?: string
  messageId?: string
}

export type EvaluationBatch = Record<string, EvaluationDetail>

function isNotFoundError(error: unknown): boolean {
  const status = (error as { response?: { status?: number } })?.response?.status
  return status === 404
}

function dedupeBoundedMessageIds(messageIds: string[]): string[] {
  const unique = [...new Set(messageIds)]
  if (unique.length > 100) {
    throw new Error('Evidence evaluation batch is limited to 100 message IDs')
  }
  if (unique.some((messageId) => !messageId.trim() || messageId.length > 512)) {
    throw new Error('Evidence evaluation message IDs must be 1–512 characters')
  }
  return unique
}

function selectorParams(selector: EvaluationSelector): Record<string, string> {
  const entries = [
    ['artifact_id', selector.artifactId],
    ['message_id', selector.messageId],
  ].filter((entry): entry is [string, string] => typeof entry[1] === 'string')
  if (entries.length !== 1 || !entries[0][1].trim() || entries[0][1].length > 512) {
    throw new Error('Provide exactly one bounded evaluation selector')
  }
  return Object.fromEntries(entries)
}

export const evaluationsApi = {
  get: async (runId: string, notebookId: string): Promise<EvaluationDetail> => {
    const response = await apiClient.get<EvaluationDetail>(
      `/evaluations/${encodeURIComponent(runId)}`,
      { params: { notebook_id: notebookId }, headers: { 'x-skip-error-toast': '1' } },
    )
    return response.data
  },
  latest: async (
    notebookId: string,
    selector: EvaluationSelector,
  ): Promise<EvaluationDetail | null> => {
    try {
      const response = await apiClient.get<EvaluationDetail>(
        '/evaluations/latest',
        {
          params: { notebook_id: notebookId, ...selectorParams(selector) },
          headers: { 'x-skip-error-toast': '1' },
        },
      )
      return response.data
    } catch (error) {
      if (isNotFoundError(error)) return null
      throw error
    }
  },
  latestBatch: async (
    notebookId: string,
    messageIds: string[],
  ): Promise<EvaluationBatch> => {
    const boundedIds = dedupeBoundedMessageIds(messageIds)
    if (boundedIds.length === 0) return {}
    const response = await apiClient.post<EvaluationBatch>(
      '/evaluations/latest/batch',
      { notebook_id: notebookId, message_ids: boundedIds },
      { headers: { 'x-skip-error-toast': '1' } },
    )
    return response.data
  },
  recheck: async (payload: EvaluationRecheckRequest): Promise<EvaluationDetail> => {
    const response = await apiClient.post<EvaluationDetail>('/evaluations/recheck', payload)
    return response.data
  },
}

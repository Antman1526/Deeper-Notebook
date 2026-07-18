import apiClient from './client'

export type ResearchDecision = 'accepted' | 'rejected' | 'pending'

export interface ResearchCandidate {
  candidate_id: string
  url: string
  title: string | null
  domain: string
  snippet: string | null
  search_query: string | null
  decision: ResearchDecision
}

export interface ResearchRun {
  id: string
  notebook_id: string
  objective: string
  stage: string
  plan: Record<string, unknown>
  hypotheses: string[]
  search_query: string | null
  candidates: ResearchCandidate[]
  source_ids: string[]
  errors: string[]
  cancelled: boolean
  comparison: {
    agreements: Array<Record<string, unknown>>
    contradictions: Array<Record<string, unknown>>
    gaps: string[]
  }
}

export const researchApi = {
  create: async (notebookId: string, objective: string) =>
    (await apiClient.post<ResearchRun>(`/notebooks/${encodeURIComponent(notebookId)}/research-runs`, { objective })).data,
  get: async (notebookId: string, runId: string) =>
    (await apiClient.get<ResearchRun>(`/notebooks/${encodeURIComponent(notebookId)}/research-runs/${encodeURIComponent(runId)}`)).data,
  approve: async (notebookId: string, runId: string, acceptedCandidateIds: string[]) =>
    (await apiClient.post<ResearchRun>(`/notebooks/${encodeURIComponent(notebookId)}/research-runs/${encodeURIComponent(runId)}/approve`, { accepted_candidate_ids: acceptedCandidateIds })).data,
  cancel: async (notebookId: string, runId: string) =>
    (await apiClient.post<ResearchRun>(`/notebooks/${encodeURIComponent(notebookId)}/research-runs/${encodeURIComponent(runId)}/cancel`)).data,
  resume: async (notebookId: string, runId: string) =>
    (await apiClient.post<ResearchRun>(`/notebooks/${encodeURIComponent(notebookId)}/research-runs/${encodeURIComponent(runId)}/resume`)).data,
}

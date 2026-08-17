// v0.8.97 — ExamLab: timed exam attempts over Evidence Studio quiz artifacts.
import apiClient from './client'

export interface ExamOption {
  id: string
  text: string
}

export interface ExamTakingQuestion {
  index: number
  prompt: string
  options: ExamOption[]
}

export interface ExamQuestionResult {
  index: number
  prompt: string
  options: ExamOption[]
  correct: boolean
  answered: boolean
  selected_option_id: string | null
  correct_option_id: string
  explanation: string
  citations: string[]
}

export interface ExamAttempt {
  id: string
  artifact_id: string
  notebook_id: string
  title: string
  question_count: number
  duration_sec: number
  started_at: string
  deadline: string
  submitted_at: string | null
  late: boolean | null
  correct_count: number | null
  score_percent: number | null
  seeded_indices: number[]
  // Exactly one is populated: questions while taking, results after submit.
  questions: ExamTakingQuestion[] | null
  results: ExamQuestionResult[] | null
}

export interface ExamAttemptSummary {
  id: string
  artifact_id: string
  notebook_id: string
  title: string
  question_count: number
  duration_sec: number
  started_at: string
  submitted_at: string | null
  late: boolean | null
  correct_count: number | null
  score_percent: number | null
}

export interface SeedMissesResult {
  created: number
  already_seeded: number
  seeded_indices: number[]
}

export const studyExamsApi = {
  start: async (artifactId: string, durationSec: number) =>
    (await apiClient.post<ExamAttempt>('/study/exams/attempts', {
      artifact_id: artifactId,
      duration_sec: durationSec,
    })).data,
  get: async (attemptId: string) =>
    (await apiClient.get<ExamAttempt>(
      `/study/exams/attempts/${encodeURIComponent(attemptId)}`,
    )).data,
  submit: async (attemptId: string, answers: Record<string, string>) =>
    (await apiClient.post<ExamAttempt>(
      `/study/exams/attempts/${encodeURIComponent(attemptId)}/submit`,
      { answers },
    )).data,
  seedMisses: async (attemptId: string) =>
    (await apiClient.post<SeedMissesResult>(
      `/study/exams/attempts/${encodeURIComponent(attemptId)}/seed-misses`,
      {},
    )).data,
  listRecent: async (notebookId?: string, limit = 20) =>
    (await apiClient.get<ExamAttemptSummary[]>('/study/exams/attempts', {
      params: { notebook_id: notebookId || undefined, limit },
    })).data,
}

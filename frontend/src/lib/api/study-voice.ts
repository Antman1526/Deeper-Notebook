import apiClient from './client'

export type StudyVoiceCapabilityState = 'ready' | 'unavailable'

export interface StudyVoiceCapability {
  stt: StudyVoiceCapabilityState
  tts: StudyVoiceCapabilityState
}

export interface StudyVoiceTranscription {
  transcript: string
}

function validatePlanId(planId: string): string {
  if (typeof planId !== 'string' || !planId.startsWith('study_plan:') || planId.length > 512 || !planId.slice('study_plan:'.length).trim()) {
    throw new Error('Invalid Study voice plan')
  }
  return planId
}

function decodeTranscription(value: unknown): StudyVoiceTranscription {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid Study voice response')
  const transcript = (value as { transcript?: unknown }).transcript
  if (typeof transcript !== 'string' || !transcript.trim() || new TextEncoder().encode(transcript).byteLength > 16 * 1024) {
    throw new Error('Invalid Study voice response')
  }
  return { transcript }
}

export const studyVoiceApi = {
  async transcribe(
    planId: string,
    audio: Blob,
    durationSeconds?: number,
    signal?: AbortSignal,
  ): Promise<StudyVoiceTranscription> {
    const form = new FormData()
    form.append('audio', audio, 'study-question.webm')
    if (durationSeconds !== undefined && Number.isFinite(durationSeconds)) form.append('duration_seconds', String(durationSeconds))
    const response = await apiClient.post(`/study/plans/${encodeURIComponent(validatePlanId(planId))}/voice:transcribe`, form, {
      signal,
      headers: { 'x-skip-error-toast': '1' },
    })
    return decodeTranscription(response.data)
  },

  async synthesize(planId: string, text: string, signal?: AbortSignal): Promise<Blob> {
    validatePlanId(planId)
    if (typeof text !== 'string' || !text.trim() || new TextEncoder().encode(text).byteLength > 8 * 1024) throw new Error('Invalid Study voice text')
    const response = await apiClient.post(`/study/plans/${encodeURIComponent(planId)}/voice:synthesize`, { text }, {
      signal,
      responseType: 'blob',
      headers: { 'x-skip-error-toast': '1' },
    })
    if (!(response.data instanceof Blob) || !response.data.type.startsWith('audio/')) throw new Error('Invalid Study voice audio')
    return response.data
  },
}

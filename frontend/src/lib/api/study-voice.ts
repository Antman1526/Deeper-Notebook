import apiClient from './client'

export type StudyVoiceCapabilityState = 'ready' | 'unavailable'

export interface StudyVoiceCapability {
  stt: StudyVoiceCapabilityState
  tts: StudyVoiceCapabilityState
}

export interface StudyVoiceTranscription {
  transcript: string
}

const SAFE_AUDIO_TYPES = new Set([
  'audio/aac',
  'audio/flac',
  'audio/mp4',
  'audio/mpeg',
  'audio/ogg',
  'audio/wav',
  'audio/webm',
  'audio/x-flac',
  'audio/x-wav',
])
const MAX_TTS_BYTES = 10 * 1024 * 1024

function decodeCapability(value: unknown): StudyVoiceCapability {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid Study voice capability')
  const candidate = value as { stt?: unknown; tts?: unknown }
  if (
    Object.keys(value).sort().join(',') !== 'stt,tts'
    || (candidate.stt !== 'ready' && candidate.stt !== 'unavailable')
    || (candidate.tts !== 'ready' && candidate.tts !== 'unavailable')
  ) {
    throw new Error('Invalid Study voice capability')
  }
  return { stt: candidate.stt as StudyVoiceCapabilityState, tts: candidate.tts as StudyVoiceCapabilityState }
}

function validatePlanId(planId: string): string {
  if (typeof planId !== 'string' || planId.length > 512) {
    throw new Error('Invalid Study voice plan')
  }
  let normalized = planId
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const decoded = decodeURIComponent(normalized)
      if (decoded === normalized) break
      normalized = decoded
    } catch {
      throw new Error('Invalid Study voice plan')
    }
  }
  if (!normalized.startsWith('study_plan:') || !normalized.slice('study_plan:'.length).trim()) {
    throw new Error('Invalid Study voice plan')
  }
  return normalized
}

function decodeTranscription(value: unknown): StudyVoiceTranscription {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid Study voice response')
  const transcript = (value as { transcript?: unknown }).transcript
  if (
    Object.keys(value).sort().join(',') !== 'transcript'
    || typeof transcript !== 'string'
    || !transcript.trim()
    || new TextEncoder().encode(transcript).byteLength > 16 * 1024
  ) {
    throw new Error('Invalid Study voice response')
  }
  return { transcript }
}

export const studyVoiceApi = {
  async capability(planId: string, signal?: AbortSignal): Promise<StudyVoiceCapability> {
    const response = await apiClient.get(`/study/plans/${encodeURIComponent(validatePlanId(planId))}/voice:capability`, {
      signal,
      headers: { 'x-skip-error-toast': '1' },
    })
    return decodeCapability(response.data)
  },

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
    const normalizedPlanId = validatePlanId(planId)
    if (typeof text !== 'string' || !text.trim() || new TextEncoder().encode(text).byteLength > 8 * 1024) throw new Error('Invalid Study voice text')
    const response = await apiClient.post(`/study/plans/${encodeURIComponent(normalizedPlanId)}/voice:synthesize`, { text }, {
      signal,
      responseType: 'blob',
      headers: { 'x-skip-error-toast': '1' },
    })
    if (
      !(response.data instanceof Blob)
      || !SAFE_AUDIO_TYPES.has(response.data.type.toLowerCase())
      || response.data.size > MAX_TTS_BYTES
    ) throw new Error('Invalid Study voice audio')
    return response.data
  },
}

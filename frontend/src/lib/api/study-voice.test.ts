import { describe, expect, it, vi } from 'vitest'

const client = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('./client', () => ({ default: client }))

import { studyVoiceApi } from './study-voice'

describe('studyVoiceApi strict response boundaries', () => {
  it('rejects capability provider metadata outside the exact receipt', async () => {
    client.get.mockResolvedValueOnce({ data: { stt: 'ready', tts: 'ready', provider: 'ollama' } })
    await expect(studyVoiceApi.capability('study_plan:one')).rejects.toThrow('Invalid Study voice capability')
  })

  it('rejects transcription provider metadata outside the exact transcript', async () => {
    client.post.mockResolvedValueOnce({ data: { transcript: 'Question', provider: 'ollama' } })
    await expect(studyVoiceApi.transcribe('study_plan:one', new Blob(['audio'], { type: 'audio/webm' }))).rejects.toThrow('Invalid Study voice response')
  })
})

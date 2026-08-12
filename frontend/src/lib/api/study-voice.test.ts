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

  it('rejects synthesized audio outside the server MIME and byte bounds', async () => {
    client.post.mockResolvedValueOnce({ data: new Blob(['audio'], { type: 'audio/x-custom' }) })
    await expect(studyVoiceApi.synthesize('study_plan:one', 'Answer')).rejects.toThrow('Invalid Study voice audio')

    client.post.mockResolvedValueOnce({
      data: new Blob([new Uint8Array(10 * 1024 * 1024 + 1)], { type: 'audio/wav' }),
    })
    await expect(studyVoiceApi.synthesize('study_plan:one', 'Answer')).rejects.toThrow('Invalid Study voice audio')
  })
})

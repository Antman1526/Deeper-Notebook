import { beforeEach, describe, expect, it, vi } from 'vitest'

const client = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('./client', () => ({ default: client }))

import { studyVoiceApi } from './study-voice'

describe('studyVoiceApi strict response boundaries', () => {
  beforeEach(() => vi.clearAllMocks())

  it('normalizes an encoded route-param plan id before capability dispatch', async () => {
    client.get.mockResolvedValueOnce({ data: { stt: 'unavailable', tts: 'unavailable' } })

    await expect(studyVoiceApi.capability('study_plan%3Aone')).resolves.toEqual({ stt: 'unavailable', tts: 'unavailable' })
    expect(client.get).toHaveBeenCalledWith(
      '/study/plans/study_plan%3Aone/voice:capability',
      expect.anything(),
    )
  })

  it('normalizes at most two encoded route-param layers', async () => {
    client.get.mockResolvedValueOnce({ data: { stt: 'unavailable', tts: 'unavailable' } })

    await expect(studyVoiceApi.capability('study_plan%253Aone')).resolves.toEqual({ stt: 'unavailable', tts: 'unavailable' })
    expect(client.get).toHaveBeenCalledWith(
      '/study/plans/study_plan%3Aone/voice:capability',
      expect.anything(),
    )
  })

  it('normalizes an encoded route-param plan id before transcription dispatch', async () => {
    client.post.mockResolvedValueOnce({ data: { transcript: 'Question' } })

    await expect(
      studyVoiceApi.transcribe('study_plan%3Aone', new Blob(['audio'], { type: 'audio/webm' })),
    ).resolves.toEqual({ transcript: 'Question' })
    expect(client.post).toHaveBeenCalledWith(
      '/study/plans/study_plan%3Aone/voice:transcribe',
      expect.any(FormData),
      expect.anything(),
    )
  })

  it('normalizes an encoded route-param plan id before synthesis dispatch', async () => {
    const audio = new Blob(['audio'], { type: 'audio/wav' })
    client.post.mockResolvedValueOnce({ data: audio })

    await expect(studyVoiceApi.synthesize('study_plan%3Aone', 'Answer')).resolves.toBe(audio)
    expect(client.post).toHaveBeenCalledWith(
      '/study/plans/study_plan%3Aone/voice:synthesize',
      { text: 'Answer' },
      expect.anything(),
    )
  })

  it('rejects malformed plan ids before dispatch', async () => {
    await expect(studyVoiceApi.capability('study_plan%ZZone')).rejects.toThrow('Invalid Study voice plan')
    await expect(studyVoiceApi.transcribe('study_plan%ZZone', new Blob(['audio'], { type: 'audio/webm' }))).rejects.toThrow(
      'Invalid Study voice plan',
    )
    await expect(studyVoiceApi.synthesize('study_plan%ZZone', 'Answer')).rejects.toThrow('Invalid Study voice plan')
    expect(client.get).not.toHaveBeenCalled()
    expect(client.post).not.toHaveBeenCalled()
  })

  it('rejects plan ids encoded more than twice before dispatch', async () => {
    const overEncodedPlanId = 'study_plan%25253Aone'

    await expect(studyVoiceApi.capability(overEncodedPlanId)).rejects.toThrow('Invalid Study voice plan')
    await expect(studyVoiceApi.transcribe(overEncodedPlanId, new Blob(['audio'], { type: 'audio/webm' }))).rejects.toThrow(
      'Invalid Study voice plan',
    )
    await expect(studyVoiceApi.synthesize(overEncodedPlanId, 'Answer')).rejects.toThrow('Invalid Study voice plan')
    expect(client.get).not.toHaveBeenCalled()
    expect(client.post).not.toHaveBeenCalled()
  })

  it.each([
    'study_plan:one%25252Ftwo',
    'study_plan:one%2525ZZ',
    'study_plan:one%25',
    'study_plan:one\r',
    'study_plan:one\n',
    'study_plan:one\0',
    'study_plan:one%0D',
    'study_plan:one%0A',
    'study_plan:one%00',
  ])('rejects residual escapes and control characters before dispatch: %j', async (unsafePlanId) => {
    await expect(studyVoiceApi.capability(unsafePlanId)).rejects.toThrow('Invalid Study voice plan')
    await expect(
      studyVoiceApi.transcribe(unsafePlanId, new Blob(['audio'], { type: 'audio/webm' })),
    ).rejects.toThrow('Invalid Study voice plan')
    await expect(studyVoiceApi.synthesize(unsafePlanId, 'Answer')).rejects.toThrow('Invalid Study voice plan')
    expect(client.get).not.toHaveBeenCalled()
    expect(client.post).not.toHaveBeenCalled()
  })

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

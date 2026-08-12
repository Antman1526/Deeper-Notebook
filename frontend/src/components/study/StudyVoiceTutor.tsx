'use client'

import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { studyVoiceApi, type StudyVoiceCapability } from '@/lib/api/study-voice'

export interface StudyVoiceTutorProps {
  planId: string
  capability: StudyVoiceCapability
  assistantText?: string | null
  onTranscript?: (transcript: string) => void
}

type VoiceState = 'idle' | 'recording' | 'transcribing' | 'synthesizing'

const RECORDING_TYPES = ['audio/webm', 'audio/mp4', 'audio/ogg']

function safeVoiceError(error: unknown, fallback: string): string {
  const code = (error as { response?: { data?: { detail?: { code?: string } } } })?.response?.data?.detail?.code
  if (code === 'local_speech_unavailable') return 'Local speech is unavailable.'
  if (code === 'audio_too_large') return 'The recording is too large.'
  if (code === 'audio_duration_too_long') return 'The recording is too long.'
  if (code === 'voice_text_too_large') return 'This tutor response is too long for local speech.'
  if (code === 'voice_timeout') return 'Local speech did not finish. Try again.'
  if (error instanceof DOMException && error.name === 'AbortError') return 'Voice request cancelled.'
  return fallback
}

export function StudyVoiceTutor({ planId, capability, assistantText = null, onTranscript }: StudyVoiceTutorProps) {
  const [state, setState] = useState<VoiceState>('idle')
  const [transcript, setTranscript] = useState<string | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const startedAtRef = useRef<number>(0)
  const controllerRef = useRef<AbortController | null>(null)
  const cancelledRef = useRef(false)
  const operationIdRef = useRef(0)
  const audioUrlRef = useRef<string | null>(null)

  const beginOperation = () => {
    const operationId = operationIdRef.current + 1
    operationIdRef.current = operationId
    cancelledRef.current = false
    return operationId
  }

  const isCurrentOperation = (operationId: number) => operationId === operationIdRef.current && !cancelledRef.current

  const releaseStream = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }

  const revokeAudioUrl = () => {
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
    audioUrlRef.current = null
    setAudioUrl(null)
  }

  useEffect(() => () => {
    operationIdRef.current += 1
    cancelledRef.current = true
    controllerRef.current?.abort()
    try {
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
    } catch {
      // The browser may already have transitioned the recorder during unmount.
    }
    releaseStream()
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
  }, [])

  const cancel = () => {
    operationIdRef.current += 1
    cancelledRef.current = true
    controllerRef.current?.abort()
    controllerRef.current = null
    try {
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
    } catch {
      // Cancellation is best effort; the stream is still released below.
    }
    recorderRef.current = null
    releaseStream()
    chunksRef.current = []
    setState('idle')
  }

  const stopRecording = () => {
    try {
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
    } catch {
      setError('The recording could not be stopped.')
      releaseStream()
      setState('idle')
    }
  }

  const startRecording = async () => {
    if (capability.stt !== 'ready' || state !== 'idle') return
    setError(null)
    const operationId = beginOperation()
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setError('Microphone access is unavailable.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!isCurrentOperation(operationId)) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      if (typeof MediaRecorder === 'undefined') {
        stream.getTracks().forEach((track) => track.stop())
        setError('Recording is unavailable in this browser.')
        return
      }
      const mimeType = RECORDING_TYPES.find((type) => MediaRecorder.isTypeSupported?.(type))
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      streamRef.current = stream
      recorderRef.current = recorder
      chunksRef.current = []
      startedAtRef.current = Date.now()
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.onerror = () => {
        if (isCurrentOperation(operationId)) {
          setError('The recording could not be completed.')
          releaseStream()
          setState('idle')
        }
      }
      recorder.onstop = () => {
        const recordedType = recorder.mimeType || mimeType || 'audio/webm'
        const blob = new Blob(chunksRef.current, { type: recordedType })
        const duration = (Date.now() - startedAtRef.current) / 1000
        const wasCancelled = !isCurrentOperation(operationId)
        chunksRef.current = []
        recorderRef.current = null
        releaseStream()
        if (wasCancelled || !blob.size) {
          if (!wasCancelled) setState('idle')
          return
        }
        setState('transcribing')
        const controller = new AbortController()
        controllerRef.current = controller
        void studyVoiceApi.transcribe(planId, blob, duration, controller.signal)
          .then((result) => {
            if (!isCurrentOperation(operationId)) return
            setTranscript(result.transcript)
            onTranscript?.(result.transcript)
            setState('idle')
          })
          .catch((requestError: unknown) => {
            if (isCurrentOperation(operationId)) setError(safeVoiceError(requestError, 'Local transcription was unavailable.'))
            if (isCurrentOperation(operationId)) setState('idle')
          })
          .finally(() => {
            if (controllerRef.current === controller) controllerRef.current = null
          })
      }
      recorder.start()
      setState('recording')
    } catch (requestError: unknown) {
      if (isCurrentOperation(operationId)) {
        releaseStream()
        setState('idle')
        if (requestError instanceof DOMException && requestError.name === 'NotAllowedError') {
          setError('Microphone access was denied.')
        } else {
          setError('Microphone access could not be started.')
        }
      }
    }
  }

  const synthesize = async () => {
    if (capability.tts !== 'ready' || !assistantText?.trim() || state !== 'idle') return
    setError(null)
    const operationId = beginOperation()
    revokeAudioUrl()
    const controller = new AbortController()
    controllerRef.current = controller
    setState('synthesizing')
    try {
      const blob = await studyVoiceApi.synthesize(planId, assistantText, controller.signal)
      if (!isCurrentOperation(operationId)) return
      const url = URL.createObjectURL(blob)
      audioUrlRef.current = url
      setAudioUrl(url)
    } catch (requestError: unknown) {
      if (isCurrentOperation(operationId)) setError(safeVoiceError(requestError, 'Local speech synthesis was unavailable.'))
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null
      if (isCurrentOperation(operationId)) setState('idle')
    }
  }

  return (
    <Card aria-labelledby="study-voice-tutor-heading">
      <CardHeader>
        <CardTitle id="study-voice-tutor-heading" className="text-base">Spoken tutoring (optional)</CardTitle>
        <CardDescription>Use local speech as an enhancement; the text tutor remains available.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {capability.stt !== 'ready' ? <p className="text-sm text-muted-foreground">Local speech recognition is unavailable.</p> : null}
        {capability.tts !== 'ready' ? <p className="text-sm text-muted-foreground">Local speech synthesis is unavailable.</p> : null}
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={state === 'recording' ? stopRecording : () => void startRecording()} disabled={capability.stt !== 'ready' || (state !== 'idle' && state !== 'recording')}>
            {state === 'recording' ? 'Stop recording' : state === 'transcribing' ? 'Transcribing…' : 'Record question'}
          </Button>
          {state !== 'idle' ? <Button type="button" variant="outline" onClick={cancel}>Cancel voice</Button> : null}
          {assistantText?.trim() && capability.tts === 'ready' ? <Button type="button" variant="outline" onClick={() => void synthesize()} disabled={state !== 'idle'}>{state === 'synthesizing' ? 'Preparing audio…' : 'Play tutor response'}</Button> : null}
        </div>
        {state === 'transcribing' ? <p role="status" className="text-sm text-muted-foreground">Transcribing locally…</p> : null}
        {transcript ? <p className="whitespace-pre-wrap rounded-md border bg-muted/30 p-3 text-sm" aria-label="Spoken question">{transcript}</p> : null}
        {audioUrl ? <audio controls src={audioUrl} onEnded={revokeAudioUrl} aria-label="Tutor response audio" /> : null}
        {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      </CardContent>
    </Card>
  )
}

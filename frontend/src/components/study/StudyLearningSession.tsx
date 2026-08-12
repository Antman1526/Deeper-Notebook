'use client'

import { useEffect, useState } from 'react'

import { TutorDock } from '@/components/study/TutorDock'
import { StudyVoiceTutor } from '@/components/study/StudyVoiceTutor'
import { studyVoiceApi, type StudyVoiceCapability } from '@/lib/api/study-voice'

export interface StudyLearningSessionProps {
  planId: string
  sourceIds?: readonly string[]
  unitId?: string | null
  approvedNetworkScope?: readonly string[]
  voiceCapability?: StudyVoiceCapability
}
/** The Learn tab's single foreground session; specialists are selected inside the dock. */
export function StudyLearningSession({
  planId,
  sourceIds = [],
  unitId = null,
  approvedNetworkScope = [],
  voiceCapability,
}: StudyLearningSessionProps) {
  const [discoveredCapability, setDiscoveredCapability] = useState<StudyVoiceCapability>(
    voiceCapability ?? { stt: 'unavailable', tts: 'unavailable' },
  )
  const [voiceTranscript, setVoiceTranscript] = useState<string | null>(null)
  const [assistantText, setAssistantText] = useState<string | null>(null)

  useEffect(() => {
    if (voiceCapability) {
      setDiscoveredCapability(voiceCapability)
      return
    }
    const controller = new AbortController()
    setDiscoveredCapability({ stt: 'unavailable', tts: 'unavailable' })
    void studyVoiceApi.capability(planId, controller.signal)
      .then((capability) => setDiscoveredCapability(capability))
      .catch(() => {
        // Voice is optional. A capability/network error must leave the text
        // tutor usable and keep every speech control closed.
      })
    return () => controller.abort()
  }, [planId, voiceCapability])

  return (
    <section aria-labelledby="study-learning-session-heading" className="space-y-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Learn</p>
        <h2 id="study-learning-session-heading" className="text-xl font-semibold">Learning session</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Ask one foreground tutor for a cited explanation, coaching, or a bounded proposal. The original sources remain read-only.
        </p>
      </div>
      <TutorDock
        planId={planId}
        sourceIds={sourceIds}
        unitId={unitId}
        approvedNetworkScope={approvedNetworkScope}
        voiceTranscript={voiceTranscript}
        onAssistantAnswer={setAssistantText}
      />
      <StudyVoiceTutor
        planId={planId}
        capability={discoveredCapability}
        assistantText={assistantText}
        onTranscript={setVoiceTranscript}
      />
    </section>
  )
}

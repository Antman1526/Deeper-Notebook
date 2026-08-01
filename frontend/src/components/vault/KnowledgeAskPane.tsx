'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useAsk } from '@/lib/hooks/use-ask'
import { useModelDefaults } from '@/lib/hooks/use-models'

interface KnowledgeAskPaneProps {
  selectedDocumentIds: string[]
  readinessReason?: string | null
}

export function KnowledgeAskPane({
  selectedDocumentIds,
  readinessReason = null,
}: KnowledgeAskPaneProps) {
  const [question, setQuestion] = useState('')
  const ask = useAsk()
  const { data: modelDefaults } = useModelDefaults()
  const modelId = modelDefaults?.default_chat_model ?? null
  const unavailableReason = readinessReason ?? (modelId ? null : 'No local research model is ready')
  const disabled = Boolean(unavailableReason) || ask.isStreaming || !question.trim()
  const selectionLabel = `${selectedDocumentIds.length} selected document${selectedDocumentIds.length === 1 ? '' : 's'}`

  const submit = () => {
    if (disabled || !modelId) return
    ask.sendAsk(question, {
      strategy: modelId,
      answer: modelId,
      finalAnswer: modelId,
    })
  }

  return (
    <section aria-label="Knowledge Ask" className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">Ask</h2>
        <p className="text-sm text-muted-foreground">{selectionLabel}</p>
      </div>
      {unavailableReason && <p role="status" className="text-sm text-muted-foreground">{unavailableReason}</p>}
      <Textarea
        aria-label="Question for selected knowledge"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        disabled={ask.isStreaming || Boolean(unavailableReason)}
        placeholder="Ask about the selected knowledge"
      />
      <Button type="button" onClick={submit} disabled={disabled}>
        Ask selected knowledge
      </Button>
      {ask.error && <p role="alert" className="text-sm text-destructive">{ask.error}</p>}
      {ask.finalAnswer && <div className="whitespace-pre-wrap text-sm">{ask.finalAnswer}</div>}
    </section>
  )
}

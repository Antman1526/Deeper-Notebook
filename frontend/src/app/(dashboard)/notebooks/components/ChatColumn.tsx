'use client'

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { notebooksApi } from '@/lib/api/notebooks'
import { useNotebookChat } from '@/lib/hooks/useNotebookChat'
import { useNotes } from '@/lib/hooks/use-notes'
import { ChatPanel } from '@/components/source/ChatPanel'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { Card, CardContent } from '@/components/ui/card'
import { ContextSelections } from '../[id]/page'
import { useTranslation } from '@/lib/hooks/use-translation'
import { SourceListResponse } from '@/lib/types/api'

interface ChatColumnProps {
  notebookId: string
  contextSelections: ContextSelections
  sources: SourceListResponse[]
  sourcesLoading: boolean
}

export function ChatColumn({ notebookId, contextSelections, sources, sourcesLoading }: ChatColumnProps) {
  const { t } = useTranslation()

  // Fetch notes for this notebook
  const { data: notes = [], isLoading: notesLoading } = useNotes(notebookId)

  const contextCountsEnabled = !sourcesLoading
    && !notesLoading
    && sources.every((source) => Object.hasOwn(contextSelections.sources, source.id))
    && notes.every((note) => Object.hasOwn(contextSelections.notes, note.id))

  // Initialize notebook chat hook
  const chat = useNotebookChat({
    notebookId,
    sources,
    notes,
    contextSelections,
    contextCountsEnabled,
  })

  // v0.8.74 — corpus-grounded starter questions for the empty chat state
  // (improvement roadmap, Batch 1). Only fetched when there are sources and no
  // messages yet; the endpoint is best-effort (returns [] on any failure), so a
  // failed query simply shows no chips. retry:false keeps it cheap/quiet.
  const showSuggestions = sources.length > 0 && chat.messages.length === 0
  const { data: suggestedQuestions = [] } = useQuery({
    queryKey: ['suggested-questions', notebookId],
    queryFn: () => notebooksApi.suggestedQuestions(notebookId, 4),
    enabled: showSuggestions,
    staleTime: 5 * 60 * 1000,
    retry: false,
  })

  // Calculate context stats for indicator
  const contextStats = useMemo(() => {
    let sourcesInsights = 0
    let sourcesFull = 0
    let notesCount = 0
    // v0.8.89 — names of the sources currently in context, for the chat
    // "Using X of Y sources" indicator + its popover (per-source filtering
    // is the off/insights/full toggle; this just makes it visible).
    const contextSourceTitles: string[] = []

    // Count sources by mode
    sources.forEach(source => {
      const mode = contextSelections.sources[source.id]
      if (mode === 'insights') {
        sourcesInsights++
        contextSourceTitles.push(source.title || '(untitled)')
      } else if (mode === 'full') {
        sourcesFull++
        contextSourceTitles.push(source.title || '(untitled)')
      }
    })

    // Count notes that are included (not 'off')
    notes.forEach(note => {
      const mode = contextSelections.notes[note.id]
      if (mode === 'full') {
        notesCount++
      }
    })

    return {
      sourcesInsights,
      sourcesFull,
      notesCount,
      totalSources: sources.length,
      contextSourceTitles,
      tokenCount: chat.tokenCount,
      charCount: chat.charCount
    }
  }, [sources, notes, contextSelections, chat.tokenCount, chat.charCount])

  // Show loading state while sources/notes are being fetched
  if (sourcesLoading || notesLoading) {
    return (
      <Card className="h-full flex flex-col">
        <CardContent className="flex-1 flex items-center justify-center">
          <LoadingSpinner size="lg" />
        </CardContent>
      </Card>
    )
  }

  // v0.7.191 — Removed dead `if (!sources && !notes)` branch.
  // Both `sources` (prop) and `notes` (useNotes default = []) are
  // ALWAYS truthy arrays, so this branch could never render. The
  // "unable to load chat" message + the t('chat.unableToLoadChat')
  // translation key were unreachable. If we ever want a real
  // load-failure UI, it should branch on `useNotes(...).error`,
  // not on falsy-array.

  return (
    <ChatPanel
      title={t('chat.chatWithNotebook')}
      contextType="notebook"
      messages={chat.messages}
      isStreaming={chat.isSending}
      contextIndicators={null}
      onSendMessage={(message, modelOverride) => chat.sendMessage(message, modelOverride)}
      suggestedQuestions={showSuggestions ? suggestedQuestions : undefined}
      onSuggestedQuestionClick={(question) => chat.sendMessage(question)}
      onCancelStreaming={chat.cancelStreaming}
      // v0.8.63 — privacy review sheet "Re-ask allowing cloud": re-send the
      // question with the fail-closed gate bypassed (explicit user consent).
      onReaskAllowCloud={(message) => chat.sendMessage(message, undefined, true)}
      modelOverride={chat.currentSession?.model_override ?? chat.pendingModelOverride ?? undefined}
      onModelChange={(model) => chat.setModelOverride(model ?? null)}
      sessions={chat.sessions}
      currentSessionId={chat.currentSessionId}
      onCreateSession={(title) => chat.createSession(title)}
      onSelectSession={chat.switchSession}
      onUpdateSession={(sessionId, title) => chat.updateSession(sessionId, { title })}
      onDeleteSession={chat.deleteSession}
      loadingSessions={chat.loadingSessions}
      notebookContextStats={contextStats}
      notebookId={notebookId}
      // v0.8.46 — wire the per-conversation MCP tool picker (v0.8.42/43).
      disabledMcpServers={chat.disabledMcpServers}
      onToggleMcpServer={chat.toggleDisabledMcpServer}
      // v0.8.97 — Debate mode: per-conversation toggle; each turn sent while
      // active carries chat_mode 'debate' (source-grounded opposition).
      debateMode={chat.debateMode}
      onToggleDebateMode={() => chat.setDebateMode(!chat.debateMode)}
    />
  )
}

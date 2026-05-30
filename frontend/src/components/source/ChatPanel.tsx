'use client'

import { useState, useRef, useEffect, useId } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Bot, User, Send, Loader2, FileText, Lightbulb, StickyNote, Clock } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  SourceChatMessage,
  SourceChatContextIndicator,
  BaseChatSession
} from '@/lib/types/api'
import { ModelSelector } from './ModelSelector'
import { McpToolPicker } from '@/components/chat/McpToolPicker'
import { ContextIndicator } from '@/components/common/ContextIndicator'
import { SessionManager } from '@/components/source/SessionManager'
import { MessageActions } from '@/components/source/MessageActions'
import { convertReferencesToCompactMarkdown, createCompactReferenceLinkComponent } from '@/lib/utils/source-references'
import { splitCitations } from '@/lib/utils/citations'
import { CitationPill } from '@/components/chat/CitationPill'
// v0.8.35c — small "local"/"cloud" chip next to AI messages, lit when
// the smart router (v0.8.0) actually ran for this notebook turn.
// Reads from the TanStack Query cache populated by useNotebookChat on
// the /chat/stream `done` event; renders null for source-chat (no
// cache entry) and pre-v0.8.1 sessions.
import { ChatMessageProviderBadge } from '@/components/chat/ChatMessageProviderBadge'
import { ChatMessagePrivacyBadge } from '@/components/chat/ChatMessagePrivacyBadge'
import { ChatMessageAgentStateBadge } from '@/components/chat/ChatMessageAgentStateBadge'
import { useModalManager } from '@/lib/hooks/use-modal-manager'
import { toast } from 'sonner'
import { useTranslation } from '@/lib/hooks/use-translation'

interface NotebookContextStats {
  sourcesInsights: number
  sourcesFull: number
  notesCount: number
  tokenCount?: number
  charCount?: number
}

interface ChatPanelProps {
  messages: SourceChatMessage[]
  isStreaming: boolean
  contextIndicators: SourceChatContextIndicator | null
  onSendMessage: (message: string, modelOverride?: string) => void
  modelOverride?: string
  onModelChange?: (model?: string) => void
  // Session management props
  sessions?: BaseChatSession[]
  currentSessionId?: string | null
  onCreateSession?: (title: string) => void
  onSelectSession?: (sessionId: string) => void
  onDeleteSession?: (sessionId: string) => void
  onUpdateSession?: (sessionId: string, title: string) => void
  loadingSessions?: boolean
  // Generic props for reusability
  title?: string
  contextType?: 'source' | 'notebook'
  // Notebook context stats (for notebook chat)
  notebookContextStats?: NotebookContextStats
  // Notebook ID for saving notes
  notebookId?: string
  // v0.8.46 — MCP tool picker wiring. Optional so callers that don't
  // care (or have no MCP servers) simply omit them — the picker
  // self-hides when there are no enabled servers. `disabledMcpServers`
  // is the current per-conversation disable list; `onToggleMcpServer`
  // flips one server's state. Both come straight from
  // useNotebookChat / useSourceChat (v0.8.42-v0.8.44b). Pre-v0.8.46
  // the <McpToolPicker> existed + was tested but was never mounted,
  // so the entire feature chain was unreachable from the UI.
  disabledMcpServers?: string[]
  onToggleMcpServer?: (name: string) => void
  // v0.8.63 — "Re-ask allowing cloud" handler for the privacy review sheet.
  // Given the original question text, re-sends it with the privacy gate
  // bypassed (explicit user consent). Only notebook chat provides it; source
  // chat omits it (no privacy badge there), so the review popover is
  // review-only in that case.
  onReaskAllowCloud?: (message: string) => void
}

export function ChatPanel({
  messages,
  isStreaming,
  contextIndicators,
  onSendMessage,
  modelOverride,
  onModelChange,
  sessions = [],
  currentSessionId,
  onCreateSession,
  onSelectSession,
  onDeleteSession,
  onUpdateSession,
  loadingSessions = false,
  title,
  contextType = 'source',
  notebookContextStats,
  notebookId,
  disabledMcpServers,
  onToggleMcpServer,
  onReaskAllowCloud,
}: ChatPanelProps) {
  const { t } = useTranslation()
  const chatInputId = useId()
  const [input, setInput] = useState('')
  const [sessionManagerOpen, setSessionManagerOpen] = useState(false)
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { openModal } = useModalManager()

  const handleReferenceClick = (type: string, id: string) => {
    const modalType = type === 'source_insight' ? 'insight' : type as 'source' | 'note' | 'insight'

    try {
      openModal(modalType, id)
      // Note: The modal system uses URL parameters and doesn't throw errors for missing items.
      // The modal component itself will handle displaying "not found" states.
      // This try-catch is here for future enhancements or unexpected errors.
    } catch {
      toast.error(t('common.noResults'))
    }
  }

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    if (input.trim() && !isStreaming) {
      onSendMessage(input.trim(), modelOverride)
      setInput('')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Detect platform for correct modifier key
    const isMac = typeof navigator !== 'undefined' && navigator.userAgent.toUpperCase().indexOf('MAC') >= 0
    const isModifierPressed = isMac ? e.metaKey : e.ctrlKey

    if (e.key === 'Enter' && isModifierPressed) {
      e.preventDefault()
      handleSend()
    }
  }

  // Detect platform for placeholder text
  const isMac = typeof navigator !== 'undefined' && navigator.userAgent.toUpperCase().indexOf('MAC') >= 0
  const keyHint = isMac ? '⌘+Enter' : 'Ctrl+Enter'

  return (
    <>
    <Card className="flex flex-col h-full flex-1 overflow-hidden">
      <CardHeader className="pb-3 flex-shrink-0">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5" />
            {title || (contextType === 'source' ? t('chat.chatWith').replace('{name}', t('navigation.sources')) : t('chat.chatWith').replace('{name}', t('common.notebook')))}
          </CardTitle>
          {onSelectSession && onCreateSession && onDeleteSession && (
            <Dialog open={sessionManagerOpen} onOpenChange={setSessionManagerOpen}>
              <Button
                variant="ghost"
                size="sm"
                className="gap-2"
                onClick={() => setSessionManagerOpen(true)}
                disabled={loadingSessions}
              >
                <Clock className="h-4 w-4" />
                <span className="text-xs">{t('chat.sessions')}</span>
              </Button>
              <DialogContent className="sm:max-w-[420px] p-0 overflow-hidden">
                <DialogTitle className="sr-only">{t('chat.sessionsTitle')}</DialogTitle>
                <SessionManager
                  sessions={sessions}
                  currentSessionId={currentSessionId ?? null}
                  onCreateSession={(title) => onCreateSession?.(title)}
                  onSelectSession={(sessionId) => {
                    onSelectSession(sessionId)
                    setSessionManagerOpen(false)
                  }}
                  onUpdateSession={(sessionId, title) => onUpdateSession?.(sessionId, title)}
                  onDeleteSession={(sessionId) => onDeleteSession?.(sessionId)}
                  loadingSessions={loadingSessions}
                />
              </DialogContent>
            </Dialog>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col min-h-0 p-0">
        <ScrollArea className="flex-1 min-h-0 px-4" ref={scrollAreaRef}>
          <div className="space-y-4 py-4">
            {messages.length === 0 ? (
              <div className="text-center text-muted-foreground py-8">
                <Bot className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p className="text-sm">
                  {t('chat.startConversation').replace('{type}', contextType === 'source' ? t('navigation.sources') : t('common.notebook'))}
                </p>
                <p className="text-xs mt-2">{t('chat.askQuestions')}</p>
              </div>
            ) : (
              messages.map((message, idx) => (
                <div
                  key={message.id}
                  className={`flex gap-3 ${
                    message.type === 'human' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  {message.type === 'ai' && (
                    <div className="flex-shrink-0">
                      <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                        <Bot className="h-4 w-4" />
                      </div>
                    </div>
                  )}
                  <div className="flex flex-col gap-2 max-w-[80%]">
                    <div
                      className={`rounded-lg px-4 py-2 ${
                        message.type === 'human'
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted'
                      }`}
                    >
                      {message.type === 'ai' ? (
                        <AIMessageContent
                          content={message.content}
                          onReferenceClick={handleReferenceClick}
                          messageId={message.id}
                        />
                      ) : (
                        // v0.7.25 — `break-all` breaks between any two
                        // characters, so normal English wrapped mid-word
                        // ("perfor-mance"). `break-words` only wraps
                        // at word boundaries (with overflow-wrap for
                        // unbreakable URLs/tokens).
                        <p className="text-sm break-words">{message.content}</p>
                      )}
                    </div>
                    {message.type === 'ai' && (
                      <div className="flex items-center gap-2 flex-wrap">
                        <MessageActions
                          content={message.content}
                          notebookId={notebookId}
                        />
                        {/* v0.8.35c — only shows for notebook chat
                            sessions where the smart router populated
                            the cache via /chat/stream's done event.
                            Source-chat and pre-v0.8.1 sessions render
                            null naturally (no cache entry). */}
                        <ChatMessageProviderBadge messageId={message.id} />
                        {/* v0.8.61 — "On-device" chip when the privacy gate
                            kept this turn local. Renders null unless
                            privacy_gated === true in the cached done event. */}
                        <ChatMessagePrivacyBadge
                          messageId={message.id}
                          // v0.8.63 — re-ask the PRECEDING user question with
                          // the privacy gate bypassed (explicit consent). Only
                          // when the host wired onReaskAllowCloud (notebook
                          // chat) and a preceding human message exists.
                          onReask={
                            onReaskAllowCloud &&
                            idx > 0 &&
                            messages[idx - 1]?.type === 'human'
                              ? () =>
                                  onReaskAllowCloud(messages[idx - 1].content)
                              : undefined
                          }
                        />
                        {/* v0.8.62 — agent-FSM "needs input"/"truncated" chip;
                            null unless ONP_AGENT_FSM surfaced a non-complete
                            terminal state on the done event. */}
                        <ChatMessageAgentStateBadge messageId={message.id} />
                      </div>
                    )}
                  </div>
                  {message.type === 'human' && (
                    <div className="flex-shrink-0">
                      <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center">
                        <User className="h-4 w-4 text-primary-foreground" />
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
            {isStreaming && (
              <div className="flex gap-3 justify-start">
                <div className="flex-shrink-0">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                    <Bot className="h-4 w-4" />
                  </div>
                </div>
                <div className="rounded-lg px-4 py-2 bg-muted">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Context Indicators */}
        {contextIndicators && (
          <div className="border-t px-4 py-2">
            <div className="flex flex-wrap gap-2 text-xs">
              {contextIndicators.sources?.length > 0 && (
                <Badge variant="outline" className="gap-1">
                  <FileText className="h-3 w-3" />
                  {contextIndicators.sources.length} {t('navigation.sources')}
                </Badge>
              )}
              {contextIndicators.insights?.length > 0 && (
                <Badge variant="outline" className="gap-1">
                  <Lightbulb className="h-3 w-3" />
                  {contextIndicators.insights.length} {contextIndicators.insights.length === 1 ? t('common.insight') : t('common.insights')}
                </Badge>
              )}
              {contextIndicators.notes?.length > 0 && (
                <Badge variant="outline" className="gap-1">
                  <StickyNote className="h-3 w-3" />
                  {contextIndicators.notes.length} {contextIndicators.notes.length === 1 ? t('common.note') : t('common.notes')}
                </Badge>
              )}
            </div>
          </div>
        )}

        {/* Notebook Context Indicator */}
        {notebookContextStats && (
          <ContextIndicator
            sourcesInsights={notebookContextStats.sourcesInsights}
            sourcesFull={notebookContextStats.sourcesFull}
            notesCount={notebookContextStats.notesCount}
            tokenCount={notebookContextStats.tokenCount}
            charCount={notebookContextStats.charCount}
          />
        )}

        {/* Input Area */}
        <div className="flex-shrink-0 p-4 space-y-3 border-t">
          {/* Model selector + v0.8.46 MCP tool picker on one row.
              The picker self-hides when there are no enabled MCP
              servers, so the row collapses to just the model selector
              for users without MCP configured. */}
          {(onModelChange || onToggleMcpServer) && (
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{t('chat.model')}</span>
                {onModelChange && (
                  <ModelSelector
                    currentModel={modelOverride}
                    onModelChange={onModelChange}
                    disabled={isStreaming}
                  />
                )}
              </div>
              {onToggleMcpServer && (
                <McpToolPicker
                  disabled={disabledMcpServers ?? []}
                  onToggle={onToggleMcpServer}
                />
              )}
            </div>
          )}

          <div className="flex gap-2 items-end min-w-0">
            <Textarea
              id={chatInputId}
              name="chat-message"
              autoComplete="off"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`${t('chat.sendPlaceholder')} (${t('chat.pressToSend').replace('{key}', keyHint)})`}
              disabled={isStreaming}
              className="flex-1 min-h-[40px] max-h-[100px] resize-none py-2 px-3 min-w-0"
              rows={1}
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              size="icon"
              className="h-[40px] w-[40px] flex-shrink-0"
            >
              {isStreaming ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    </>
  )
}

// Helper component to render AI messages with clickable references
// v0.8.0 Phase 4 Task 14 — split on citation markers before markdown rendering.
// [mcp:N] markers are rendered as CitationPill components inline; [source/note/insight:ID]
// markers within text segments are handled by the existing compact-reference system.
// v0.8.1 Item 3 — messageId passed through to CitationPill so the MCP
// popover can look up tool-call payloads from the TanStack Query cache.
function AIMessageContent({
  content,
  onReferenceClick,
  messageId,
}: {
  content: string
  onReferenceClick: (type: string, id: string) => void
  messageId?: string
}) {
  const { t } = useTranslation()

  // Create custom link component for compact references
  const LinkComponent = createCompactReferenceLinkComponent(onReferenceClick)

  // Shared ReactMarkdown component overrides — reused per text segment.
  const mdComponents = {
    a: LinkComponent,
    p: ({ children }: { children?: React.ReactNode }) => <p className="mb-4">{children}</p>,
    h1: ({ children }: { children?: React.ReactNode }) => <h1 className="mb-4 mt-6">{children}</h1>,
    h2: ({ children }: { children?: React.ReactNode }) => <h2 className="mb-3 mt-5">{children}</h2>,
    h3: ({ children }: { children?: React.ReactNode }) => <h3 className="mb-3 mt-4">{children}</h3>,
    h4: ({ children }: { children?: React.ReactNode }) => <h4 className="mb-2 mt-4">{children}</h4>,
    h5: ({ children }: { children?: React.ReactNode }) => <h5 className="mb-2 mt-3">{children}</h5>,
    h6: ({ children }: { children?: React.ReactNode }) => <h6 className="mb-2 mt-3">{children}</h6>,
    li: ({ children }: { children?: React.ReactNode }) => <li className="mb-1">{children}</li>,
    ul: ({ children }: { children?: React.ReactNode }) => <ul className="mb-4 space-y-1">{children}</ul>,
    ol: ({ children }: { children?: React.ReactNode }) => <ol className="mb-4 space-y-1">{children}</ol>,
    table: ({ children }: { children?: React.ReactNode }) => (
      <div className="my-4 overflow-x-auto">
        <table className="min-w-full border-collapse border border-border">{children}</table>
      </div>
    ),
    thead: ({ children }: { children?: React.ReactNode }) => <thead className="bg-muted">{children}</thead>,
    tbody: ({ children }: { children?: React.ReactNode }) => <tbody>{children}</tbody>,
    tr: ({ children }: { children?: React.ReactNode }) => <tr className="border-b border-border">{children}</tr>,
    th: ({ children }: { children?: React.ReactNode }) => <th className="border border-border px-3 py-2 text-left font-semibold">{children}</th>,
    td: ({ children }: { children?: React.ReactNode }) => <td className="border border-border px-3 py-2">{children}</td>,
  }

  // Split the raw content on ALL citation markers ([mcp:N], [source:ID], etc.).
  // Text segments are rendered via ReactMarkdown (with compact-reference conversion).
  // Citation segments are rendered as CitationPill components inline.
  const segments = splitCitations(content)

  // v0.7.25 — was `prose-a:text-blue-600 prose-a:break-all`. The
  // hardcoded blue-600 fails WCAG AA against the dark muted
  // background in dark themes (~3.2:1), and break-all hyphenates
  // URLs mid-character. Theme-aware token + break-words.
  return (
    <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none break-words prose-headings:font-semibold prose-a:text-primary dark:prose-a:text-blue-400 prose-a:underline prose-a:break-words prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-p:mb-4 prose-p:leading-7 prose-li:mb-2">
      {segments.map((seg, idx) => {
        if (seg.kind === 'text') {
          // Pass text segments through the existing compact-reference pipeline.
          const markdownWithCompactRefs = convertReferencesToCompactMarkdown(
            seg.value,
            t('common.references')
          )
          return (
            <ReactMarkdown
              key={idx}
              remarkPlugins={[remarkGfm]}
              components={mdComponents}
            >
              {markdownWithCompactRefs}
            </ReactMarkdown>
          )
        }
        // Citation segment → render as an inline pill.
        // v0.8.1 Item 3 — pass messageId so MCP pills can look up
        // tool-call payloads from the TanStack Query cache.
        return (
          <CitationPill key={`${seg.kind}-${idx}`} kind={seg.kind} value={seg.value} messageId={messageId} />
        )
      })}
    </div>
  )
}

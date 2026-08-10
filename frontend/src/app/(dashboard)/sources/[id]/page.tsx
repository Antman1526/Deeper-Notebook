'use client'

import { useRouter, useParams } from 'next/navigation'
import { useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { ArrowLeft } from 'lucide-react'
import { FolioRouteFrame } from '@/components/deeper-notebook/folio/FolioRouteFrame'
import { AppShell } from '@/components/layout/AppShell'
import { useSourceChat } from '@/lib/hooks/useSourceChat'
import { ChatPanel } from '@/components/source/ChatPanel'
import { useNavigation } from '@/lib/hooks/use-navigation'
import { SourceDetailContent } from '@/components/source/SourceDetailContent'

export default function SourceDetailPage() {
  const router = useRouter()
  const params = useParams()
  const sourceId = params?.id ? decodeURIComponent(params.id as string) : ''
  const navigation = useNavigation()

  // Initialize source chat
  const chat = useSourceChat(sourceId)

  const handleBack = useCallback(() => {
    const returnPath = navigation.getReturnPath()
    router.push(returnPath)
    navigation.clearReturnTo()
  }, [navigation, router])

  return (
    <AppShell>
      <FolioRouteFrame section="Collect" title="Source record">
        <div className="flex min-h-[32rem] flex-col">
      {/* v0.7.164 — Source detail layout polish.
          Before: back button had `pt-6 pb-4 px-6` PLUS its own
          `mb-4` (~80px of empty space above content). Each column
          re-applied `px-4 pb-6` inside an already-padded parent —
          40px of horizontal padding squeezed the chat column on
          standard laptop widths. Visual audit item #2.
          After: tightened back-button band to `px-6 pt-4 pb-2`
          (removed the redundant mb-4 on the Button itself), and
          dropped the per-column `px-4` so the outer `px-6` does
          all the horizontal work. Chat column gains back ~32px of
          breathing room on every viewport. */}
          <div className="px-6 pt-4 pb-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleBack}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {navigation.getReturnLabel()}
        </Button>
          </div>

      {/* Main content: Source detail + Chat */}
          <div className="grid min-h-0 flex-1 gap-6 overflow-hidden px-6 lg:grid-cols-[2fr_1fr]">
        {/* Left column - Source detail */}
        <div className="overflow-y-auto pb-6">
          <SourceDetailContent
            sourceId={sourceId}
            showChatButton={false}
            onClose={handleBack}
          />
        </div>

        {/* Right column - Chat */}
        <div className="overflow-y-auto pb-6">
          <ChatPanel
            messages={chat.messages}
            isStreaming={chat.isStreaming}
            contextIndicators={chat.contextIndicators}
            onSendMessage={(message, model) => chat.sendMessage(message, model)}
            modelOverride={chat.currentSession?.model_override ?? chat.pendingModelOverride ?? undefined}
            onModelChange={(model) => {
              chat.setModelOverride(model ?? null)
            }}
            sessions={chat.sessions}
            currentSessionId={chat.currentSessionId}
            onCreateSession={(title) => chat.createSession({ title })}
            onSelectSession={chat.switchSession}
            onUpdateSession={(sessionId, title) => chat.updateSession(sessionId, { title })}
            onDeleteSession={chat.deleteSession}
            loadingSessions={chat.loadingSessions}
            // v0.8.46 — wire the per-conversation MCP tool picker
            // (v0.8.44/44b source-chat parity).
            disabledMcpServers={chat.disabledMcpServers}
            onToggleMcpServer={chat.toggleDisabledMcpServer}
          />
        </div>
          </div>
        </div>
      </FolioRouteFrame>
    </AppShell>
  )
}

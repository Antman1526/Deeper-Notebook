'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { AppShell } from '@/components/layout/AppShell'
import { NotebookHeader } from '../components/NotebookHeader'
import { SourcesColumn } from '../components/SourcesColumn'
import { NotesColumn } from '../components/NotesColumn'
import { ChatColumn } from '../components/ChatColumn'
import { useNotebook } from '@/lib/hooks/use-notebooks'
import { useNotebookSources } from '@/lib/hooks/use-sources'
import { useNotes } from '@/lib/hooks/use-notes'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { ArtifactRail } from '@/components/onp'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'
import { useIsDesktop } from '@/lib/hooks/use-media-query'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { FileText, StickyNote, MessageSquare } from 'lucide-react'

export type ContextMode = 'off' | 'insights' | 'full'

export interface ContextSelections {
  sources: Record<string, ContextMode>
  notes: Record<string, ContextMode>
}

export default function NotebookPage() {
  const { t } = useTranslation()
  const params = useParams()

  // Ensure the notebook ID is properly decoded from URL
  const notebookId = params?.id ? decodeURIComponent(params.id as string) : ''

  const { data: notebook, isLoading: notebookLoading } = useNotebook(notebookId)
  const {
    sources,
    isLoading: sourcesLoading,
    refetch: refetchSources,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useNotebookSources(notebookId)
  const { data: notes, isLoading: notesLoading } = useNotes(notebookId)

  // Get collapse states for dynamic layout
  const { sourcesCollapsed, notesCollapsed } = useNotebookColumnsStore()

  // Detect desktop to avoid double-mounting ChatColumn
  const isDesktop = useIsDesktop()

  // Mobile tab state (Sources, Notes, or Chat)
  const [mobileActiveTab, setMobileActiveTab] = useState<'sources' | 'notes' | 'chat'>('chat')

  // Context selection state
  const [contextSelections, setContextSelections] = useState<ContextSelections>({
    sources: {},
    notes: {}
  })

  // v0.7.64 — reset context selections whenever the user navigates to
  // a different notebook. Previously the state survived navigation
  // because it's plain useState (not keyed on notebookId), so stale
  // source/note IDs from a previous notebook accumulated. The init
  // effects below only ADD keys; they never prune. When the chat then
  // built context, `Source.get(stale_id)` would 404 on the backend —
  // mostly silently, but it's a wasted round-trip and in source_chat
  // it could short-circuit the prompt build.
  useEffect(() => {
    setContextSelections({ sources: {}, notes: {} })
  }, [notebookId])

  // Initialize and update selections when sources load or change.
  // v0.7.64 — also PRUNE keys for sources that are no longer in the
  // list (deleted source, filter change, etc.). The previous version
  // only added new keys, so a deleted source would linger in the
  // selection map indefinitely.
  useEffect(() => {
    if (sources && sources.length > 0) {
      setContextSelections(prev => {
        const validIds = new Set(sources.map(s => s.id))
        const newSourceSelections: Record<string, ContextMode> = {}
        // Carry forward only keys still in the current source list.
        for (const [id, mode] of Object.entries(prev.sources)) {
          if (validIds.has(id)) newSourceSelections[id] = mode
        }
        sources.forEach(source => {
          const currentMode = newSourceSelections[source.id]
          const hasInsights = source.insights_count > 0

          if (currentMode === undefined) {
            // Initial setup - default based on insights availability
            newSourceSelections[source.id] = hasInsights ? 'insights' : 'full'
          } else if (currentMode === 'full' && hasInsights) {
            // Source gained insights while in 'full' mode - auto-switch to 'insights'
            newSourceSelections[source.id] = 'insights'
          }
        })
        return { ...prev, sources: newSourceSelections }
      })
    }
  }, [sources])

  useEffect(() => {
    if (notes && notes.length > 0) {
      setContextSelections(prev => {
        // v0.7.64 — prune stale note IDs same as sources above.
        const validIds = new Set(notes.map(n => n.id))
        const newNoteSelections: Record<string, ContextMode> = {}
        for (const [id, mode] of Object.entries(prev.notes)) {
          if (validIds.has(id)) newNoteSelections[id] = mode
        }
        notes.forEach(note => {
          // Only set default if not already set
          if (!(note.id in newNoteSelections)) {
            // Notes default to 'full'
            newNoteSelections[note.id] = 'full'
          }
        })
        return { ...prev, notes: newNoteSelections }
      })
    }
  }, [notes])

  // Handler to update context selection
  const handleContextModeChange = (itemId: string, mode: ContextMode, type: 'source' | 'note') => {
    setContextSelections(prev => ({
      ...prev,
      [type === 'source' ? 'sources' : 'notes']: {
        ...(type === 'source' ? prev.sources : prev.notes),
        [itemId]: mode
      }
    }))
  }

  if (notebookLoading) {
    // v0.7.25 — wrap loading state in AppShell so the sidebar doesn't
    // disappear during the notebook fetch. Previously this returned a
    // bare <div>, causing a visible layout flash on every navigation
    // and a UX dead-end if the request hung.
    return (
      <AppShell>
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner size="lg" />
        </div>
      </AppShell>
    )
  }

  if (!notebook) {
    return (
      <AppShell>
        <div className="p-6">
          <h1 className="text-2xl font-bold mb-4">{t('notebooks.notFound')}</h1>
          <p className="text-muted-foreground">{t('notebooks.notFoundDesc')}</p>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      {/* v0.7.164 — Notebook detail page header gets a clean visual
          break from the 3-column workspace below.
          Before: header was `p-6 pb-0` (no bottom padding, no
          divider) and the workspace was `p-6 pt-6`. The two regions
          read as one blob — the user couldn't immediately see where
          the metadata header ends and the source/notes/chat columns
          begin.
          After: header gets `pb-4` (real breathing room) plus a
          hairline `border-b` divider; workspace re-balances to
          `pt-8` so the columns "land" cleanly below the divider.
          This is the most-visited screen in the app — worth the
          polish to compete with NotebookLM's notebook view. */}
      <div className="flex flex-col flex-1 min-h-0">
        <div className="flex-shrink-0 px-6 pt-6 pb-4 border-b">
          <NotebookHeader notebook={notebook} />
        </div>

        <div className="flex-1 px-6 pt-8 pb-6 overflow-x-auto flex flex-col">
          <ArtifactRail
            notebookId={notebookId}
            sources={sources}
            sourcesLoading={sourcesLoading}
          />

          {/* Mobile: Tabbed interface - only render on mobile to avoid double-mounting */}
          {!isDesktop && (
            <>
              <div className="lg:hidden mb-4">
                <Tabs value={mobileActiveTab} onValueChange={(value) => setMobileActiveTab(value as 'sources' | 'notes' | 'chat')}>
                  <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="sources" className="gap-2">
                      <FileText className="h-4 w-4" />
                      {t('navigation.sources')}
                    </TabsTrigger>
                    <TabsTrigger value="notes" className="gap-2">
                      <StickyNote className="h-4 w-4" />
                      {t('common.notes')}
                    </TabsTrigger>
                    <TabsTrigger value="chat" className="gap-2">
                      <MessageSquare className="h-4 w-4" />
                      {t('common.chat')}
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>

              {/* Mobile: Show only active tab */}
              <div className="flex-1 overflow-hidden lg:hidden">
                {mobileActiveTab === 'sources' && (
                  <SourcesColumn
                    sources={sources}
                    isLoading={sourcesLoading}
                    notebookId={notebookId}
                    notebookName={notebook?.name}
                    onRefresh={refetchSources}
                    contextSelections={contextSelections.sources}
                    onContextModeChange={(sourceId, mode) => handleContextModeChange(sourceId, mode, 'source')}
                    hasNextPage={hasNextPage}
                    isFetchingNextPage={isFetchingNextPage}
                    fetchNextPage={fetchNextPage}
                  />
                )}
                {mobileActiveTab === 'notes' && (
                  <NotesColumn
                    notes={notes}
                    isLoading={notesLoading}
                    notebookId={notebookId}
                    contextSelections={contextSelections.notes}
                    onContextModeChange={(noteId, mode) => handleContextModeChange(noteId, mode, 'note')}
                  />
                )}
                {mobileActiveTab === 'chat' && (
                  <ChatColumn
                    notebookId={notebookId}
                    contextSelections={contextSelections}
                    sources={sources}
                    sourcesLoading={sourcesLoading}
                  />
                )}
              </div>
            </>
          )}

          {/* Desktop: Collapsible columns layout */}
          <div className={cn(
            'hidden lg:flex h-full min-h-0 gap-6 transition-all duration-150',
            'flex-row'
          )}>
            {/* Sources Column */}
            {/* v0.7.25 — was `flex-none basis-1/3` which doesn't shrink.
                Two of those + chat's flex-1 + sidebar + gap-6 ×2 + p-6
                overflowed the viewport at the lg breakpoint (1024px),
                triggering the parent's overflow-x-auto and giving a
                horizontal scrollbar on common laptop sizes. Switched to
                flex-1 basis-0 min-w-0 so columns shrink proportionally. */}
            <div className={cn(
              'transition-all duration-150',
              sourcesCollapsed ? 'w-12 flex-shrink-0' : 'flex-1 basis-0 min-w-0'
            )}>
              <SourcesColumn
                sources={sources}
                isLoading={sourcesLoading}
                notebookId={notebookId}
                notebookName={notebook?.name}
                onRefresh={refetchSources}
                contextSelections={contextSelections.sources}
                onContextModeChange={(sourceId, mode) => handleContextModeChange(sourceId, mode, 'source')}
                hasNextPage={hasNextPage}
                isFetchingNextPage={isFetchingNextPage}
                fetchNextPage={fetchNextPage}
              />
            </div>

            {/* Notes Column */}
            <div className={cn(
              'transition-all duration-150',
              notesCollapsed ? 'w-12 flex-shrink-0' : 'flex-1 basis-0 min-w-0'
            )}>
              <NotesColumn
                notes={notes}
                isLoading={notesLoading}
                notebookId={notebookId}
                contextSelections={contextSelections.notes}
                onContextModeChange={(noteId, mode) => handleContextModeChange(noteId, mode, 'note')}
              />
            </div>

            {/* Chat Column - always expanded, takes remaining space.
                v0.7.25 — removed the `lg:-mr-6` negative margin that
                cancelled `lg:pr-6` for no visible benefit, just to
                clip focus rings. */}
            <div className="transition-all duration-150 flex-[2] min-w-0">
              <ChatColumn
                notebookId={notebookId}
                contextSelections={contextSelections}
                sources={sources}
                sourcesLoading={sourcesLoading}
              />
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  )
}

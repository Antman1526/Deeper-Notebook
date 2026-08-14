'use client'

import { useState, useEffect, useRef } from 'react'
import type { ImperativePanelHandle } from 'react-resizable-panels'
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
import { ArtifactRail } from '@/components/deeper-notebook'
import { FolioRouteFrame } from '@/components/deeper-notebook/folio/FolioRouteFrame'
import { ResearchRunWorkspace } from '@/components/research/ResearchRunWorkspace'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'
import { useIsDesktop } from '@/lib/hooks/use-media-query'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { FileText, StickyNote, MessageSquare } from 'lucide-react'
import {
  applyBulkNoteContext,
  applyBulkSourceContext,
  computeNoteSelections,
  computeSourceSelections,
  type NoteContextDefault,
  type SourceBulkAction,
  type SourceContextDefault,
} from '@/lib/utils/source-context'

// Re-exported for compatibility with older notebook child imports.
import type { ContextMode, ContextSelections } from '@/lib/types/notebook-context'
export type { ContextMode, ContextSelections }

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
  const { sourcesCollapsed, notesCollapsed, setSources, setNotes } =
    useNotebookColumnsStore()

  // v0.8.85 — resizable workspace: imperative refs to the sources/notes panels
  // so the existing collapse buttons (which flip the store) stay in sync with
  // the React Flow… er, react-resizable-panels collapse state, and vice-versa.
  const sourcesPanelRef = useRef<ImperativePanelHandle>(null)
  const notesPanelRef = useRef<ImperativePanelHandle>(null)

  // Store → panel: when the column's collapse button toggles the store, drive
  // the panel. Guarded by isCollapsed() so the onCollapse/onExpand callbacks
  // (panel → store) don't loop.
  useEffect(() => {
    const p = sourcesPanelRef.current
    if (!p) return
    if (sourcesCollapsed && !p.isCollapsed()) p.collapse()
    else if (!sourcesCollapsed && p.isCollapsed()) p.expand()
  }, [sourcesCollapsed])
  useEffect(() => {
    const p = notesPanelRef.current
    if (!p) return
    if (notesCollapsed && !p.isCollapsed()) p.collapse()
    else if (!notesCollapsed && p.isCollapsed()) p.expand()
  }, [notesCollapsed])

  // Detect desktop to avoid double-mounting ChatColumn
  const isDesktop = useIsDesktop()

  // Mobile tab state (Sources, Notes, or Chat)
  const [mobileActiveTab, setMobileActiveTab] = useState<'sources' | 'notes' | 'chat'>('chat')

  // Context selection state
  const [contextSelections, setContextSelections] = useState<ContextSelections>({
    sources: {},
    notes: {}
  })
  const [sourceContextDefault, setSourceContextDefault] = useState<SourceContextDefault>('include')
  const [noteContextDefault, setNoteContextDefault] = useState<NoteContextDefault>('include')

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
    setSourceContextDefault('include')
    setNoteContextDefault('include')
  }, [notebookId])

  // Initialize and update selections when sources load or change.
  // v0.7.64 — also PRUNE keys for sources that are no longer in the
  // list (deleted source, filter change, etc.). The previous version
  // only added new keys, so a deleted source would linger in the
  // selection map indefinitely.
  useEffect(() => {
    if (sources && sources.length > 0) {
      setContextSelections(prev => ({
        ...prev,
        sources: computeSourceSelections(prev.sources, sources, sourceContextDefault),
      }))
    }
  }, [sources, sourceContextDefault])

  useEffect(() => {
    if (notes && notes.length > 0) {
      setContextSelections(prev => ({
        ...prev,
        notes: computeNoteSelections(prev.notes, notes, noteContextDefault),
      }))
    }
  }, [notes, noteContextDefault])

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

  const handleBulkSourceContext = (action: SourceBulkAction) => {
    setSourceContextDefault(action)
    setContextSelections(prev => ({
      ...prev,
      sources: applyBulkSourceContext(prev.sources, sources ?? [], action),
    }))
  }

  const handleBulkNoteContext = (action: NoteContextDefault) => {
    setNoteContextDefault(action)
    setContextSelections(prev => ({
      ...prev,
      notes: applyBulkNoteContext(prev.notes, notes ?? [], action),
    }))
  }

  if (notebookLoading) {
    // v0.7.25 — wrap loading state in AppShell so the sidebar doesn't
    // disappear during the notebook fetch. Previously this returned a
    // bare <div>, causing a visible layout flash on every navigation
    // and a UX dead-end if the request hung.
    return (
      <AppShell>
        <FolioRouteFrame section="Organize" title="Notebook workspace">
          <div className="flex flex-1 items-center justify-center">
            <LoadingSpinner size="lg" />
          </div>
        </FolioRouteFrame>
      </AppShell>
    )
  }

  if (!notebook) {
    return (
      <AppShell>
        <FolioRouteFrame section="Organize" title="Notebook workspace">
          <div>
            <h2 className="mb-4 text-2xl font-semibold">{t('notebooks.notFound')}</h2>
            <p className="text-muted-foreground">{t('notebooks.notFoundDesc')}</p>
          </div>
        </FolioRouteFrame>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <FolioRouteFrame section="Organize" title="Notebook workspace">
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
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex-shrink-0 px-6 pt-6 pb-4 border-b">
          <NotebookHeader notebook={notebook} />
        </div>

        <div className="flex-1 px-6 pt-8 pb-6 overflow-x-auto flex flex-col">
          <ResearchRunWorkspace notebookId={notebookId} />
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
                    onBulkContextModeChange={handleBulkSourceContext}
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
                    onBulkContextModeChange={handleBulkNoteContext}
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

          {/* Desktop: resizable 3-pane workspace (v0.8.85 — roadmap Batch 3).
              Draggable handles; widths remembered via autoSaveId (localStorage).
              Sources/Notes panels are collapsible and stay in sync with the
              notebook-columns store (the in-column collapse buttons still work;
              dragging a pane shut also updates the store via onCollapse). */}
          {isDesktop && <div className="hidden lg:flex h-full min-h-0 flex-1">
            <ResizablePanelGroup
              direction="horizontal"
              autoSaveId="onp-notebook-workspace"
              className="h-full"
            >
              <ResizablePanel
                ref={sourcesPanelRef}
                collapsible
                collapsedSize={4}
                minSize={12}
                defaultSize={28}
                onCollapse={() => setSources(true)}
                onExpand={() => setSources(false)}
                className="min-w-0"
              >
                <div className="h-full pr-3">
                  <SourcesColumn
                    sources={sources}
                    isLoading={sourcesLoading}
                    notebookId={notebookId}
                    notebookName={notebook?.name}
                    onRefresh={refetchSources}
                    contextSelections={contextSelections.sources}
                    onContextModeChange={(sourceId, mode) => handleContextModeChange(sourceId, mode, 'source')}
                    onBulkContextModeChange={handleBulkSourceContext}
                    hasNextPage={hasNextPage}
                    isFetchingNextPage={isFetchingNextPage}
                    fetchNextPage={fetchNextPage}
                  />
                </div>
              </ResizablePanel>

              <ResizableHandle withHandle />

              <ResizablePanel
                ref={notesPanelRef}
                collapsible
                collapsedSize={4}
                minSize={12}
                defaultSize={28}
                onCollapse={() => setNotes(true)}
                onExpand={() => setNotes(false)}
                className="min-w-0"
              >
                <div className="h-full px-3">
                  <NotesColumn
                    notes={notes}
                    isLoading={notesLoading}
                    notebookId={notebookId}
                    contextSelections={contextSelections.notes}
                    onContextModeChange={(noteId, mode) => handleContextModeChange(noteId, mode, 'note')}
                    onBulkContextModeChange={handleBulkNoteContext}
                  />
                </div>
              </ResizablePanel>

              <ResizableHandle withHandle />

              {/* Chat — always expanded, takes the remaining space. */}
              <ResizablePanel defaultSize={44} minSize={25} className="min-w-0">
                <div className="h-full pl-3">
                  <ChatColumn
                    notebookId={notebookId}
                    contextSelections={contextSelections}
                    sources={sources}
                    sourcesLoading={sourcesLoading}
                  />
                </div>
              </ResizablePanel>
            </ResizablePanelGroup>
          </div>}
        </div>
      </div>
      </FolioRouteFrame>
    </AppShell>
  )
}

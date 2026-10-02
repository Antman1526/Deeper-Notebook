'use client'

import { useState, useEffect, useRef } from 'react'
import type { ImperativePanelHandle } from 'react-resizable-panels'
import { useParams } from 'next/navigation'
import { NotebookHeader } from '../components/NotebookHeader'
import { SourcesColumn } from '../components/SourcesColumn'
import { NotesColumn } from '../components/NotesColumn'
import { ChatColumn } from '../components/ChatColumn'
import { StudioColumn } from '../components/StudioColumn'
import { useNotebook } from '@/lib/hooks/use-notebooks'
import { useNotebookSources } from '@/lib/hooks/use-sources'
import { useNotes } from '@/lib/hooks/use-notes'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { FolioRouteFrame } from '@/components/deeper-notebook/folio/FolioRouteFrame'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'
import { useIsDesktop, useIsWideDesktop } from '@/lib/hooks/use-media-query'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { FileText, StickyNote, MessageSquare, Sparkles } from 'lucide-react'
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
  const { sourcesCollapsed, notesCollapsed, studioCollapsed, setSources, setNotes, setStudio } =
    useNotebookColumnsStore()

  // v0.8.85 — resizable workspace: imperative refs to the sources/notes panels
  // so the existing collapse buttons (which flip the store) stay in sync with
  // the React Flow… er, react-resizable-panels collapse state, and vice-versa.
  const sourcesPanelRef = useRef<ImperativePanelHandle>(null)
  const notesPanelRef = useRef<ImperativePanelHandle>(null)
  const studioPanelRef = useRef<ImperativePanelHandle>(null)

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
  useEffect(() => {
    const p = studioPanelRef.current
    if (!p) return
    if (studioCollapsed && !p.isCollapsed()) p.collapse()
    else if (!studioCollapsed && p.isCollapsed()) p.expand()
  }, [studioCollapsed])

  // Detect desktop to avoid double-mounting ChatColumn
  const isDesktop = useIsDesktop()
  const isWideDesktop = useIsWideDesktop()
  // Compact desktops (1024–1279px): Notes and Studio share one tabbed side panel.
  const [sideTab, setSideTab] = useState<'notes' | 'studio'>('notes')
  // v0.8.130 — useIsDesktop is false on the first render (SSR-safe), so a desktop
  // load used to mount the mobile chat for one tick before the desktop one: a
  // duplicate round of session, note and context requests whose firing depended on
  // timing. Render the columns only once the viewport is known (the media-query
  // effect above and this one commit together).
  const [viewportKnown, setViewportKnown] = useState(false)
  useEffect(() => setViewportKnown(true), [])

  // Mobile tab state (Sources, Chat, Notes, or Studio)
  type MobileTab = 'sources' | 'chat' | 'notes' | 'studio'
  const [mobileActiveTab, setMobileActiveTab] = useState<MobileTab>('chat')

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
      <>
        <FolioRouteFrame section="Organize" title="Notebook workspace">
          <div className="flex flex-1 items-center justify-center">
            <LoadingSpinner size="lg" />
          </div>
        </FolioRouteFrame>
      </>
    )
  }

  if (!notebook) {
    return (
      <>
        <FolioRouteFrame section="Organize" title="Notebook workspace">
          <div>
            <h2 className="mb-4 text-2xl font-semibold">{t('notebooks.notFound')}</h2>
            <p className="text-muted-foreground">{t('notebooks.notFoundDesc')}</p>
          </div>
        </FolioRouteFrame>
      </>
    )
  }

  const sourcesColumn = (
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
  )
  const notesColumn = (
    <NotesColumn
      notes={notes}
      isLoading={notesLoading}
      notebookId={notebookId}
      contextSelections={contextSelections.notes}
      onContextModeChange={(noteId, mode) => handleContextModeChange(noteId, mode, 'note')}
      onBulkContextModeChange={handleBulkNoteContext}
    />
  )
  const chatColumn = (
    <ChatColumn
      notebookId={notebookId}
      contextSelections={contextSelections}
      sources={sources}
      sourcesLoading={sourcesLoading}
    />
  )
  const studioColumn = (
    <StudioColumn notebookId={notebookId} sources={sources} sourcesLoading={sourcesLoading} />
  )

  // v0.8.130 — Phase 2a: the workspace is its own bounded page. It used to sit in a
  // folio titled "Notebook workspace" under ~1,000px of header, Guided research and
  // the Evidence Studio band, with no height bound, so the panes never got a definite
  // height and the chat's scroll-to-bottom scrolled the whole canvas on load. Now the
  // notebook title (in NotebookHeader) is the page's single h1, the page fills the
  // canvas (workspace.css), and only the columns scroll. Guided research and the
  // Evidence Studio band moved into the Studio column.
  return (
    <>
      <main
        aria-labelledby="notebook-title"
        data-dn-notebook-workspace=""
        className="flex h-full min-h-0 min-w-0 flex-col gap-3"
      >
        <NotebookHeader notebook={notebook} />

        {viewportKnown && !isDesktop && (
          // v0.8.130 — Phase 2 exit gate: the columns sit in TabsContent so each tab controls a
          // real tabpanel (the swapped-in div left aria-controls pointing at nothing). Radix
          // mounts only the active panel, so the chat still mounts once.
          <Tabs
            value={mobileActiveTab}
            onValueChange={(value) => setMobileActiveTab(value as MobileTab)}
            className="flex min-h-0 flex-1 flex-col gap-3 lg:hidden"
          >
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="sources" className="gap-2">
                <FileText className="h-4 w-4" />
                {t('navigation.sources')}
              </TabsTrigger>
              <TabsTrigger value="chat" className="gap-2">
                <MessageSquare className="h-4 w-4" />
                {t('common.chat')}
              </TabsTrigger>
              <TabsTrigger value="notes" className="gap-2">
                <StickyNote className="h-4 w-4" />
                {t('common.notes')}
              </TabsTrigger>
              <TabsTrigger value="studio" className="gap-2">
                <Sparkles className="h-4 w-4" />
                {t('notebooks.studio')}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="sources" className="min-h-0 flex-1 overflow-hidden">{sourcesColumn}</TabsContent>
            <TabsContent value="chat" className="min-h-0 flex-1 overflow-hidden">{chatColumn}</TabsContent>
            <TabsContent value="notes" className="min-h-0 flex-1 overflow-hidden">{notesColumn}</TabsContent>
            <TabsContent value="studio" className="min-h-0 flex-1 overflow-hidden">{studioColumn}</TabsContent>
          </Tabs>
        )}

        {/* Desktop: Sources | Chat | Notes | Studio. Draggable handles; widths are
            remembered under a new autoSaveId so the old 3-pane widths don't apply.
            Sources, Notes and Studio collapse and stay in sync with the columns store. */}
        {viewportKnown && isDesktop && isWideDesktop && (
          <div className="hidden min-h-0 flex-1 lg:flex">
            <ResizablePanelGroup direction="horizontal" autoSaveId="dn-notebook-workspace-v2" className="h-full">
              <ResizablePanel
                ref={sourcesPanelRef}
                collapsible
                collapsedSize={4}
                minSize={14}
                defaultSize={20}
                onCollapse={() => setSources(true)}
                onExpand={() => setSources(false)}
                className="min-w-0"
              >
                <div className="h-full pr-1.5">{sourcesColumn}</div>
              </ResizablePanel>
              <ResizableHandle withHandle />
              <ResizablePanel defaultSize={38} minSize={28} className="min-w-0">
                <div className="h-full px-1.5">{chatColumn}</div>
              </ResizablePanel>
              <ResizableHandle withHandle />
              <ResizablePanel
                ref={notesPanelRef}
                collapsible
                collapsedSize={4}
                minSize={12}
                defaultSize={18}
                onCollapse={() => setNotes(true)}
                onExpand={() => setNotes(false)}
                className="min-w-0"
              >
                <div className="h-full px-1.5">{notesColumn}</div>
              </ResizablePanel>
              <ResizableHandle withHandle />
              <ResizablePanel
                ref={studioPanelRef}
                collapsible
                collapsedSize={4}
                // v0.8.130 — 22%, not 18%: at 18% (about 180px at 1280) the evidence
                // receipt overflowed the column and its fingerprints broke mid-value.
                minSize={22}
                defaultSize={24}
                onCollapse={() => setStudio(true)}
                onExpand={() => setStudio(false)}
                className="min-w-0"
              >
                <div className="h-full pl-1.5">{studioColumn}</div>
              </ResizablePanel>
            </ResizablePanelGroup>
          </div>
        )}

        {/* v0.8.130 — compact desktops (1024–1279px): four columns left Notes and Studio
            ~120px each and clipped their controls, so they share one side panel here. */}
        {viewportKnown && isDesktop && !isWideDesktop && (
          <div className="hidden min-h-0 flex-1 lg:flex">
            <ResizablePanelGroup direction="horizontal" autoSaveId="dn-notebook-workspace-v2-compact" className="h-full">
              <ResizablePanel
                ref={sourcesPanelRef}
                collapsible
                collapsedSize={6}
                minSize={18}
                defaultSize={28}
                onCollapse={() => setSources(true)}
                onExpand={() => setSources(false)}
                className="min-w-0"
              >
                <div className="h-full pr-1.5">{sourcesColumn}</div>
              </ResizablePanel>
              <ResizableHandle withHandle />
              <ResizablePanel defaultSize={42} minSize={30} className="min-w-0">
                <div className="h-full px-1.5">{chatColumn}</div>
              </ResizablePanel>
              <ResizableHandle withHandle />
              {/* v0.8.130 — 28%, not 22%: the shared Notes/Studio panel holds the
                  evidence receipt, which overflowed below about 210px. */}
              <ResizablePanel defaultSize={30} minSize={28} className="min-w-0">
                {/* v0.8.130 — Phase 2 exit gate: real tabpanels, as on small screens. */}
                <Tabs
                  value={sideTab}
                  onValueChange={(value) => setSideTab(value as 'notes' | 'studio')}
                  className="flex h-full min-h-0 flex-col gap-2 pl-1.5"
                >
                  <TabsList aria-label={t('notebooks.notesAndStudio')} className="grid w-full grid-cols-2">
                    <TabsTrigger value="notes" className="gap-2">
                      <StickyNote className="h-4 w-4" />
                      {t('common.notes')}
                    </TabsTrigger>
                    <TabsTrigger value="studio" className="gap-2">
                      <Sparkles className="h-4 w-4" />
                      {t('notebooks.studio')}
                    </TabsTrigger>
                  </TabsList>
                  <TabsContent value="notes" className="min-h-0 flex-1">{notesColumn}</TabsContent>
                  <TabsContent value="studio" className="min-h-0 flex-1">{studioColumn}</TabsContent>
                </Tabs>
              </ResizablePanel>
            </ResizablePanelGroup>
          </div>
        )}
      </main>
    </>
  )
}

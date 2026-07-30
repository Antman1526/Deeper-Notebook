'use client'

import { useEffect } from 'react'
import {
  BookOpen,
  Code2,
  Eye,
  FilePenLine,
  FileSearch,
  Network,
  ShieldCheck,
} from 'lucide-react'

import { OverlayDocumentView } from '@/components/overlay/OverlayDocumentView'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type {
  KnowledgePane,
  KnowledgeSourceAuthority,
  KnowledgeViewMode,
} from '@/lib/api/knowledge-workspace'
import {
  VaultPageContractError,
  type VaultMount,
} from '@/lib/api/vault'
import { useOverlayPage } from '@/lib/hooks/use-overlay'
import {
  useVaultGraph,
  useVaultOutgoing,
  useVaultPage,
} from '@/lib/hooks/use-vault'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'

import { VaultDocumentView } from './VaultDocumentView'
import { VaultGraph } from './VaultGraph'

export type KnowledgeNavigate = (
  vaultId: string,
  noteId: string,
  relativePathHint: string | undefined,
  titleHint: string | undefined,
  paneId: string | undefined,
  targetText: string | undefined,
  sourceAuthority: KnowledgeSourceAuthority,
) => void

interface KnowledgePaneContentProps {
  pane: KnowledgePane
  mounts: VaultMount[]
  onNavigate: KnowledgeNavigate
}

const shortcutModes: Record<string, KnowledgeViewMode> = {
  '1': 'reading',
  '2': 'source',
  '3': 'live-preview',
  '4': 'graph',
}

export function KnowledgePaneContent({
  pane,
  mounts,
  onNavigate,
}: KnowledgePaneContentProps) {
  const { t } = useTranslation()
  const setTabViewMode = useKnowledgeWorkspaceStore(
    (state) => state.setTabViewMode,
  )
  const reconcileTabReference = useKnowledgeWorkspaceStore(
    (state) => state.reconcileTabReference,
  )
  const activeTab = pane.tabs.find((tab) => tab.id === pane.activeTabId)
    ?? pane.tabs[0]
  const vaultId = activeTab?.vaultId
  const noteId = activeTab?.noteId
  const visibleMode = activeTab?.viewMode ?? 'reading'
  const isOverlay = activeTab?.sourceAuthority === 'overlay'
  const overlayPage = useOverlayPage(isOverlay ? noteId : undefined)
  const vaultPage = useVaultPage(
    isOverlay ? undefined : vaultId,
    isOverlay ? undefined : noteId,
  )
  const outgoing = useVaultOutgoing(
    isOverlay ? undefined : vaultId,
    isOverlay ? undefined : noteId,
  )
  const graph = useVaultGraph(
    isOverlay ? undefined : vaultId,
    isOverlay ? undefined : noteId,
    !isOverlay && visibleMode === 'graph',
  )

  useEffect(() => {
    if (!activeTab) return
    if (isOverlay) {
      if (!overlayPage.data || overlayPage.isError) return
      reconcileTabReference(pane.id, activeTab.id, {
        title: overlayPage.data.overlay.title.trim() || activeTab.title,
        relativePath: overlayPage.data.overlay.relative_path,
      })
      return
    }
    if (!vaultPage.data || vaultPage.isError) return
    reconcileTabReference(pane.id, activeTab.id, {
      title: vaultPage.data.note.title?.trim() || activeTab.title,
      relativePath: vaultPage.data.file.relative_path,
    })
  }, [
    activeTab,
    isOverlay,
    overlayPage.data,
    overlayPage.isError,
    pane.id,
    reconcileTabReference,
    vaultPage.data,
    vaultPage.isError,
  ])

  if (!activeTab) {
    return (
      <div className="p-4 sm:p-6">
        <div className="flex min-h-72 flex-col items-center justify-center rounded-md border border-dashed p-6 text-center">
          <FileSearch className="mb-3 h-8 w-8 text-muted-foreground" />
          <h2 className="font-medium">{t('knowledge.selectNote')}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('knowledge.externalReadOnly')}
          </p>
        </div>
      </div>
    )
  }

  const pageData = isOverlay ? overlayPage.data : vaultPage.data
  const pageLoading = isOverlay ? overlayPage.isLoading : vaultPage.isLoading
  const pageError = isOverlay ? overlayPage.isError : vaultPage.isError
  const mount = isOverlay
    ? undefined
    : mounts.find((candidate) => candidate.id === vaultId)
  const currentOutgoing = isOverlay
    ? overlayPage.data?.outgoing_links ?? []
    : outgoing.data || vaultPage.data?.outgoing_links || []
  const unresolved = currentOutgoing.filter((link) => !link.resolved)
  const currentGraph = isOverlay ? overlayPage.data?.graph : graph.data
  const modeOptions = [
    { mode: 'reading', label: t('knowledge.reader'), icon: BookOpen },
    { mode: 'source', label: t('knowledge.source'), icon: Code2 },
    { mode: 'live-preview', label: t('knowledge.livePreview'), icon: Eye },
    { mode: 'graph', label: t('knowledge.localGraph'), icon: Network },
  ] satisfies Array<{
    mode: KnowledgeViewMode
    label: string
    icon: typeof BookOpen
  }>

  const navigate = (targetNoteId: string) => {
    const isOverlayCenter = isOverlay
      && overlayPage.data?.note.id === targetNoteId
    const overlayLink = isOverlay
      ? overlayPage.data?.outgoing_links.find(
          (candidate) => candidate.target_note_id === targetNoteId,
        )
      : undefined
    const overlayBacklink = isOverlay
      ? overlayPage.data?.backlinks.find(
          (candidate) => candidate.source_note_id === targetNoteId,
        )
      : undefined
    const mappedOverlayBacklink = overlayBacklink?.source_overlay_note_id
      && overlayBacklink.source_relative_path
      ? overlayBacklink
      : undefined
    const link = currentOutgoing.find(
      (candidate) => candidate.target_note_id === targetNoteId,
    )
    const graphNode = currentGraph?.nodes.find(
      (candidate) => candidate.id === targetNoteId,
    )
    const titleHint = isOverlayCenter
      ? overlayPage.data?.overlay.title
      : link?.target_note_title === null
        || link?.target_note_title === undefined
        ? overlayBacklink?.source_note_title ?? graphNode?.title ?? undefined
        : link.target_note_title
    const navigationNoteId = isOverlayCenter
      ? overlayPage.data?.overlay.id
      : isOverlay
        ? overlayLink?.target_overlay_note_id
          ?? mappedOverlayBacklink?.source_overlay_note_id
        : targetNoteId
    const relativePathHint = isOverlayCenter
      ? overlayPage.data?.overlay.relative_path
      : overlayLink?.target_relative_path
        ?? mappedOverlayBacklink?.source_relative_path
        ?? link?.target_relative_path
    const targetText = isOverlayCenter
      ? overlayPage.data?.overlay.title
      : isOverlay
        ? overlayLink?.target_text
          ?? mappedOverlayBacklink?.source_note_title
          ?? targetNoteId
        : link?.target_text || targetNoteId
    if (!navigationNoteId) return
    onNavigate(
      activeTab.vaultId,
      navigationNoteId,
      relativePathHint ?? undefined,
      titleHint,
      pane.id,
      targetText,
      activeTab.sourceAuthority,
    )
  }

  const errorKey = !isOverlay && vaultPage.error instanceof VaultPageContractError
    ? vaultPage.error.code === 'canonical-path-unavailable'
      ? 'knowledge.canonicalPathUnavailable'
      : 'knowledge.pageInvalid'
    : isOverlay
      ? 'knowledge.overlay.loadError'
      : 'knowledge.loadError'
  const title = isOverlay && overlayPage.data
    ? overlayPage.data.overlay.title || activeTab.title
    : !isOverlay && vaultPage.data
      ? vaultPage.data.note.title || activeTab.title
      : activeTab.title
  const sourceDescription = isOverlay && overlayPage.data
    ? `${overlayPage.data.overlay.relative_path} · ${t('knowledge.overlay.writable')}`
    : !isOverlay && vaultPage.data
      ? `${mount?.name || activeTab.relativePath} · ${
        vaultPage.data.note.source_format || mount?.format_mode || 'markdown'
      } · ${t('knowledge.canonicalSource')}`
      : ''
  const reloadOverlayPage = async () => {
    const result = await overlayPage.refetch()
    if (result.isError || !result.data) {
      throw result.error ?? new Error('overlay_reload_failed')
    }
    return result.data
  }

  return (
    <section
      role="region"
      aria-label={`${t('knowledge.knowledgePane')} modes ${pane.id}`}
      tabIndex={0}
      onKeyDown={(event) => {
        if (
          !event.ctrlKey
          || event.shiftKey
          || event.metaKey
          || event.altKey
          || event.repeat
        ) return
        const target = event.target
        if (
          target instanceof Element
          && target.closest(
            'input, textarea, select, [contenteditable]:not([contenteditable="false"])',
          )
        ) return
        const mode = shortcutModes[event.key]
        if (!mode) return
        event.preventDefault()
        setTabViewMode(pane.id, activeTab.id, mode)
      }}
      className="flex min-h-full flex-col p-4 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:p-6"
    >
      <div
        role="toolbar"
        aria-label={`${t('knowledge.knowledgePane')} ${pane.id}`}
        className="flex w-fit flex-wrap items-center gap-1 rounded-md border bg-muted/40 p-1"
      >
        {modeOptions.map(({ mode, label, icon: Icon }) => (
          <Button
            key={mode}
            type="button"
            size="sm"
            variant={visibleMode === mode ? 'secondary' : 'ghost'}
            aria-pressed={visibleMode === mode}
            onClick={() => setTabViewMode(pane.id, activeTab.id, mode)}
          >
            <Icon aria-hidden="true" className="mr-1.5 h-4 w-4" />
            {label}
          </Button>
        ))}
      </div>

      {pageData && !pageError && (
        <div className="mt-5 border-b pb-4">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-semibold">
              {title || t('knowledge.untitledNote')}
            </h2>
            <Badge
              variant={isOverlay ? 'secondary' : 'outline'}
              className={`dn-authority-badge ${
                isOverlay
                  ? 'dn-authority-badge--overlay'
                  : 'dn-authority-badge--external'
              }`}
            >
              {isOverlay
                ? <FilePenLine aria-hidden="true" />
                : <ShieldCheck aria-hidden="true" />}
              {isOverlay
                ? t('knowledge.overlay.writable')
                : t('knowledge.overlay.externalReadOnly')}
            </Badge>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {sourceDescription}
          </p>
        </div>
      )}

      <div className="mt-5 min-h-0 flex-1">
        {pageLoading ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            {t('knowledge.noteLoading')}
          </p>
        ) : pageError ? (
          <p role="alert" className="py-12 text-center text-sm text-destructive">
            {t(errorKey)}
          </p>
        ) : isOverlay && overlayPage.data ? (
          <OverlayDocumentView
            key={`${pane.id}:${activeTab.id}`}
            viewId={`${pane.id}:${activeTab.id}`}
            mode={visibleMode}
            page={overlayPage.data}
            onNavigate={navigate}
            onReload={reloadOverlayPage}
          />
        ) : !isOverlay && vaultPage.data ? (
          visibleMode === 'graph' ? (
            graph.isLoading ? (
              <p className="py-12 text-center text-sm text-muted-foreground">
                {t('knowledge.graphLoading')}
              </p>
            ) : graph.isError ? (
              <p role="alert" className="py-12 text-center text-sm text-destructive">
                {t('knowledge.graphLoadError')}
              </p>
            ) : (
              <VaultGraph
                graph={graph.data}
                unresolved={unresolved}
                onNavigate={navigate}
              />
            )
          ) : (
            <VaultDocumentView
              viewId={`${pane.id}:${activeTab.id}`}
              mode={visibleMode}
              page={{
                ...vaultPage.data,
                outgoing_links: currentOutgoing,
              }}
              onNavigate={navigate}
            />
          )
        ) : null}
      </div>
    </section>
  )
}

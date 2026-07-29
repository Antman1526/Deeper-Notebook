'use client'

import { useEffect } from 'react'
import { BookOpen, Code2, Eye, FileSearch, Network, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type {
  KnowledgePane,
  KnowledgeViewMode,
} from '@/lib/api/knowledge-workspace'
import {
  VaultPageContractError,
  type VaultMount,
} from '@/lib/api/vault'
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
  relativePathHint?: string,
  titleHint?: string,
  paneId?: string,
  targetText?: string,
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
  const page = useVaultPage(vaultId, noteId)
  const outgoing = useVaultOutgoing(vaultId, noteId)
  const graph = useVaultGraph(vaultId, noteId, visibleMode === 'graph')

  useEffect(() => {
    if (!activeTab || !page.data || page.isError) return
    reconcileTabReference(pane.id, activeTab.id, {
      title: page.data.note.title?.trim() || activeTab.title,
      relativePath: page.data.file.relative_path,
    })
  }, [
    activeTab,
    page.data,
    page.isError,
    pane.id,
    reconcileTabReference,
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

  const mount = mounts.find((candidate) => candidate.id === vaultId)
  const currentOutgoing = outgoing.data || page.data?.outgoing_links || []
  const unresolved = currentOutgoing.filter((link) => !link.resolved)
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
    const link = currentOutgoing.find(
      (candidate) => candidate.target_note_id === targetNoteId,
    )
    const graphNode = graph.data?.nodes.find(
      (candidate) => candidate.id === targetNoteId,
    )
    const titleHint = link?.target_note_title === null
      || link?.target_note_title === undefined
      ? graphNode?.title ?? undefined
      : link.target_note_title
    onNavigate(
      activeTab.vaultId,
      targetNoteId,
      link?.target_relative_path ?? undefined,
      titleHint,
      pane.id,
      link?.target_text || targetNoteId,
    )
  }

  const errorKey = page.error instanceof VaultPageContractError
    ? page.error.code === 'canonical-path-unavailable'
      ? 'knowledge.canonicalPathUnavailable'
      : 'knowledge.pageInvalid'
    : 'knowledge.loadError'

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

      {page.data && !page.isError && (
        <div className="mt-5 border-b pb-4">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-semibold">
              {page.data.note.title || activeTab.title
                || t('knowledge.untitledNote')}
            </h2>
            <Badge variant="outline">
              <ShieldCheck className="mr-1 h-3.5 w-3.5" />
              {t('knowledge.readOnly')}
            </Badge>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {mount?.name || activeTab.relativePath}
            {' · '}
            {page.data.note.source_format || mount?.format_mode || 'markdown'}
            {' · '}
            {t('knowledge.canonicalSource')}
          </p>
        </div>
      )}

      <div className="mt-5 min-h-0 flex-1">
        {page.isLoading ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            {t('knowledge.noteLoading')}
          </p>
        ) : page.isError ? (
          <p role="alert" className="py-12 text-center text-sm text-destructive">
            {t(errorKey)}
          </p>
        ) : !page.data ? null
          : visibleMode === 'graph' ? (
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
                ...page.data,
                outgoing_links: currentOutgoing,
              }}
              onNavigate={navigate}
            />
          )}
      </div>
    </section>
  )
}

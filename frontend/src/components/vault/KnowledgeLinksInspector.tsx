'use client'

import {
  useVaultBacklinks,
  useVaultOutgoing,
  useVaultPage,
} from '@/lib/hooks/use-vault'
import { useOverlayPage } from '@/lib/hooks/use-overlay'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  useKnowledgeWorkspaceStore,
} from '@/lib/stores/knowledge-workspace-store'
import type { KnowledgeNavigate } from './KnowledgePaneContent'
import { VaultLinks } from './VaultLinks'

interface KnowledgeLinksInspectorProps {
  onNavigate: KnowledgeNavigate
}

export function KnowledgeLinksInspector({
  onNavigate,
}: KnowledgeLinksInspectorProps) {
  const { t } = useTranslation()
  const activePane = useKnowledgeWorkspaceStore(
    (state) => state.panes[state.activePaneId],
  )
  const activeTab = activePane?.tabs.find(
    (tab) => tab.id === activePane.activeTabId,
  ) ?? activePane?.tabs[0]
  const vaultId = activeTab?.vaultId
  const noteId = activeTab?.noteId
  const isOverlay = activeTab?.sourceAuthority === 'overlay'
  const overlayPage = useOverlayPage(isOverlay ? noteId : undefined)
  const page = useVaultPage(
    isOverlay ? undefined : vaultId,
    isOverlay ? undefined : noteId,
  )
  const backlinks = useVaultBacklinks(
    isOverlay ? undefined : vaultId,
    isOverlay ? undefined : noteId,
  )
  const outgoing = useVaultOutgoing(
    isOverlay ? undefined : vaultId,
    isOverlay ? undefined : noteId,
  )
  const currentBacklinks = isOverlay
    ? overlayPage.data?.backlinks ?? []
    : backlinks.data || page.data?.backlinks || []
  const currentOutgoing = isOverlay
    ? overlayPage.data?.outgoing_links ?? []
    : outgoing.data || page.data?.outgoing_links || []
  const linksLoading = Boolean(
    noteId && (
      isOverlay
        ? overlayPage.isLoading
        : backlinks.isLoading || outgoing.isLoading
    ),
  )
  const linksError = Boolean(
    noteId && (
      isOverlay
        ? overlayPage.isError
        : backlinks.isError || outgoing.isError
    ),
  )

  const navigateBacklink = (targetNoteId: string) => {
    if (!activeTab) return
    const overlayLink = isOverlay
      ? overlayPage.data?.backlinks.find(
          (candidate) => candidate.source_note_id === targetNoteId,
        )
      : undefined
    const link = currentBacklinks.find(
      (candidate) => candidate.source_note_id === targetNoteId,
    )
    const title = link?.source_note_title || targetNoteId
    const navigationNoteId = isOverlay
      ? overlayLink?.source_overlay_note_id
      : targetNoteId
    if (!navigationNoteId) return
    onNavigate(
      activeTab.vaultId,
      navigationNoteId,
      undefined,
      title,
      undefined,
      undefined,
      activeTab.sourceAuthority,
    )
  }

  const navigateOutgoing = (targetNoteId: string) => {
    if (!activeTab) return
    const overlayLink = isOverlay
      ? overlayPage.data?.outgoing_links.find(
          (candidate) => candidate.target_note_id === targetNoteId,
        )
      : undefined
    const link = currentOutgoing.find(
      (candidate) => candidate.target_note_id === targetNoteId,
    )
    const titleHint = link?.target_note_title === null
      || link?.target_note_title === undefined
      ? undefined
      : link.target_note_title
    const navigationNoteId = isOverlay
      ? overlayLink?.target_overlay_note_id
      : targetNoteId
    if (!navigationNoteId) return
    onNavigate(
      activeTab.vaultId,
      navigationNoteId,
      link?.target_relative_path ?? undefined,
      titleHint,
      undefined,
      link?.target_text || targetNoteId,
      activeTab.sourceAuthority,
    )
  }

  return (
    <aside
      className="space-y-6 border-t p-4 lg:border-l lg:border-t-0"
      aria-label={t('knowledge.noteLinks')}
    >
      {linksLoading ? (
        <p className="text-sm text-muted-foreground">
          {t('knowledge.linksLoading')}
        </p>
      ) : linksError ? (
        <p role="alert" className="text-sm text-destructive">
          {t('knowledge.linksLoadError')}
        </p>
      ) : (
        <>
          <VaultLinks
            title={t('knowledge.backlinks')}
            links={currentBacklinks}
            direction="source"
            unresolvedLabel={t('knowledge.unresolved')}
            onNavigate={navigateBacklink}
          />
          <VaultLinks
            title={t('knowledge.outgoing')}
            links={currentOutgoing}
            direction="target"
            unresolvedLabel={t('knowledge.unresolved')}
            onNavigate={navigateOutgoing}
          />
        </>
      )}
    </aside>
  )
}

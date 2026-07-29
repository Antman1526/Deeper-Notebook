'use client'

import {
  useVaultBacklinks,
  useVaultOutgoing,
  useVaultPage,
} from '@/lib/hooks/use-vault'
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
  const page = useVaultPage(vaultId, noteId)
  const backlinks = useVaultBacklinks(vaultId, noteId)
  const outgoing = useVaultOutgoing(vaultId, noteId)
  const currentBacklinks = backlinks.data || page.data?.backlinks || []
  const currentOutgoing = outgoing.data || page.data?.outgoing_links || []
  const linksLoading = Boolean(
    noteId && (backlinks.isLoading || outgoing.isLoading),
  )
  const linksError = Boolean(
    noteId && (backlinks.isError || outgoing.isError),
  )

  const navigateBacklink = (targetNoteId: string) => {
    if (!activeTab) return
    const link = currentBacklinks.find(
      (candidate) => candidate.source_note_id === targetNoteId,
    )
    const title = link?.source_note_title || targetNoteId
    onNavigate(activeTab.vaultId, targetNoteId, undefined, title)
  }

  const navigateOutgoing = (targetNoteId: string) => {
    if (!activeTab) return
    const link = currentOutgoing.find(
      (candidate) => candidate.target_note_id === targetNoteId,
    )
    const relativePath = link?.target_text || targetNoteId
    const title = link?.alias || link?.target_text || targetNoteId
    onNavigate(activeTab.vaultId, targetNoteId, relativePath, title)
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

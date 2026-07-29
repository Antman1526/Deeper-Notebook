'use client'

import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { OpenKnowledgeTab } from '@/lib/api/knowledge-workspace'
import type { VaultFile } from '@/lib/api/vault'
import {
  useHydrateKnowledgeWorkspace,
  usePersistKnowledgeWorkspace,
} from '@/lib/hooks/use-knowledge-workspace'
import {
  useScanVault,
  useVaultFiles,
  useVaults,
} from '@/lib/hooks/use-vault'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import { KnowledgeLinksInspector } from './KnowledgeLinksInspector'
import {
  KnowledgePaneContent,
  type KnowledgeNavigate,
} from './KnowledgePaneContent'
import { KnowledgeWorkspaceLayout } from './KnowledgeWorkspaceLayout'
import { VaultFileTree } from './VaultFileTree'

function titleFromRelativePath(relativePath: string): string {
  return relativePath.split('/').pop()?.replace(/\.md$/i, '') || relativePath
}

function tabFromFile(file: VaultFile): OpenKnowledgeTab {
  return {
    vaultId: file.vault_id,
    noteId: file.note_id,
    title: titleFromRelativePath(file.relative_path),
    relativePath: file.relative_path,
  }
}

function fallbackRelativePath(noteId: string, hint?: string): string {
  const normalized = hint?.trim()
  if (
    normalized
    && !/^(?:[\\/]|[A-Za-z]:)/.test(normalized)
    && !normalized.split(/[\\/]/).includes('..')
  ) {
    return normalized
  }
  const safeNoteId = noteId
    .replace(/[\\/]/g, '-')
    .replace(/\.\./g, '-')
    .trim()
  return `${safeNoteId || 'note'}.md`
}

export function KnowledgeExplorer() {
  const { t } = useTranslation()
  const hydration = useHydrateKnowledgeWorkspace()
  const persistence = usePersistKnowledgeWorkspace()
  const mounts = useVaults()
  const [vaultId, setVaultId] = useState('')
  const files = useVaultFiles(vaultId)
  const activePane = useKnowledgeWorkspaceStore(
    (state) => state.panes[state.activePaneId],
  )
  const activeTab = activePane?.tabs.find(
    (tab) => tab.id === activePane.activeTabId,
  ) ?? activePane?.tabs[0]
  const openTab = useKnowledgeWorkspaceStore((state) => state.openTab)
  const scan = useScanVault(
    vaultId,
    activeTab?.vaultId === vaultId ? activeTab.noteId : undefined,
  )

  useEffect(() => {
    if (!vaultId && mounts.data?.[0]) setVaultId(mounts.data[0].id)
  }, [mounts.data, vaultId])

  const openFile = (file: VaultFile, paneId?: string) => {
    openTab(tabFromFile(file), paneId)
  }

  const navigate: KnowledgeNavigate = (
    targetVaultId,
    targetNoteId,
    relativePathHint,
    titleHint,
    paneId,
  ) => {
    const listedFile = files.data?.find(
      (file) => file.vault_id === targetVaultId
        && file.note_id === targetNoteId,
    )
    if (listedFile) {
      openFile(listedFile, paneId)
      return
    }

    const existingTab = Object.values(
      useKnowledgeWorkspaceStore.getState().panes,
    )
      .flatMap((pane) => pane.tabs)
      .find((tab) => tab.vaultId === targetVaultId
        && tab.noteId === targetNoteId)
    if (existingTab) {
      openTab({
        vaultId: existingTab.vaultId,
        noteId: existingTab.noteId,
        title: existingTab.title,
        relativePath: existingTab.relativePath,
        viewMode: existingTab.viewMode,
      }, paneId)
      return
    }

    const relativePath = fallbackRelativePath(targetNoteId, relativePathHint)
    openTab({
      vaultId: targetVaultId,
      noteId: targetNoteId,
      title: titleHint?.trim() || titleFromRelativePath(relativePath),
      relativePath,
    }, paneId)
  }

  const selected = mounts.data?.find((mount) => mount.id === vaultId)
  const selectedNoteId = activeTab?.vaultId === vaultId
    ? activeTab.noteId
    : ''

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="border-b px-4 py-4 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">
              {t('navigation.knowledge')}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {t('knowledge.description')}
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={() => void scan.mutateAsync()}
            disabled={!vaultId || scan.isPending}
          >
            <RefreshCw
              className={`mr-2 h-4 w-4 ${scan.isPending ? 'animate-spin' : ''}`}
            />
            {t('knowledge.scan')}
          </Button>
        </div>
        <div className="mt-3 space-y-1" aria-live="polite">
          {hydration.isLoading && (
            <p role="status" className="text-sm text-muted-foreground">
              {t('knowledge.workspaceLoading')}
            </p>
          )}
          {hydration.isError && (
            <p role="alert" className="text-sm text-destructive">
              {t('knowledge.workspaceLoadError')}
            </p>
          )}
          {persistence.isPending && (
            <p role="status" className="text-sm text-muted-foreground">
              {t('knowledge.workspaceSaving')}
            </p>
          )}
          {persistence.isError && (
            <p role="alert" className="text-sm text-destructive">
              {t('knowledge.workspaceSaveError')}
            </p>
          )}
        </div>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(16rem,22rem)_minmax(0,1fr)_minmax(15rem,20rem)]">
        <aside
          className="flex min-h-64 flex-col gap-4 border-b p-4 lg:border-b-0 lg:border-r"
          aria-label={t('knowledge.files')}
        >
          <label className="text-sm font-medium" htmlFor="vault-mount">
            {t('knowledge.mounts')}
          </label>
          <select
            id="vault-mount"
            value={vaultId}
            onChange={(event) => setVaultId(event.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled={mounts.isLoading || mounts.isError}
          >
            {mounts.data?.map((mount) => (
              <option key={mount.id} value={mount.id}>
                {mount.name} · {mount.format_mode}
              </option>
            ))}
          </select>
          {mounts.isLoading ? (
            <p className="text-sm text-muted-foreground">
              {t('knowledge.mountsLoading')}
            </p>
          ) : mounts.isError ? (
            <p role="alert" className="text-sm text-destructive">
              {t('knowledge.loadError')}
            </p>
          ) : !mounts.data?.length ? (
            <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
              {t('knowledge.noMounts')}
            </p>
          ) : (
            <>
              <div className="rounded-md bg-muted p-3 text-sm">
                <span className="font-medium">{t('knowledge.status')}</span>
                <p className="mt-1 text-muted-foreground">
                  {selected?.state || t('common.unknown')}
                </p>
              </div>
              {files.isLoading ? (
                <p className="text-sm text-muted-foreground">
                  {t('knowledge.filesLoading')}
                </p>
              ) : files.isError ? (
                <p role="alert" className="text-sm text-destructive">
                  {t('knowledge.loadError')}
                </p>
              ) : (
                <VaultFileTree
                  files={files.data || []}
                  selectedNoteId={selectedNoteId}
                  onSelect={(noteId) => {
                    const file = files.data?.find(
                      (candidate) => candidate.note_id === noteId,
                    )
                    if (file) openFile(file)
                  }}
                />
              )}
            </>
          )}
        </aside>
        <main className="min-h-0 min-w-0 overflow-hidden">
          <KnowledgeWorkspaceLayout
            renderPane={(pane) => (
              <KnowledgePaneContent
                pane={pane}
                mounts={mounts.data || []}
                onNavigate={navigate}
              />
            )}
          />
        </main>
        <KnowledgeLinksInspector onNavigate={navigate} />
      </div>
    </div>
  )
}

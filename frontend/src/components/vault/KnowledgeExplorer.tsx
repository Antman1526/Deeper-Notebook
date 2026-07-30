'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
import { useTodayOverlayNote } from '@/lib/hooks/use-overlay'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'
import { KnowledgeLinksInspector } from './KnowledgeLinksInspector'
import {
  KnowledgePaneContent,
  type KnowledgeNavigate,
} from './KnowledgePaneContent'
import { KnowledgeWorkspaceLayout } from './KnowledgeWorkspaceLayout'
import { VaultFileTree } from './VaultFileTree'
import { KnowledgeCommandBridge } from './KnowledgeCommandBridge'
import { KnowledgeQuickSwitcher } from './KnowledgeQuickSwitcher'
import { CreateUniqueNoteDialog } from '../overlay/CreateUniqueNoteDialog'
import { OverlayUtilityPanel, localDateKey, tabFromOverlay } from '../overlay/OverlayUtilityPanel'

type SelectedKnowledgeRoot =
  | { authority: 'overlay'; id: 'overlay_space:default' }
  | { authority: 'external-vault'; id: string }

function titleFromRelativePath(relativePath: string): string {
  return relativePath.split('/').pop()?.replace(/\.md$/i, '') || relativePath
}

function tabFromFile(file: VaultFile): OpenKnowledgeTab {
  return {
    vaultId: file.vault_id,
    noteId: file.note_id,
    title: titleFromRelativePath(file.relative_path),
    relativePath: file.relative_path,
    sourceAuthority: 'external-vault',
  }
}

export function KnowledgeExplorer() {
  const { t } = useTranslation()
  const hydration = useHydrateKnowledgeWorkspace()
  const persistence = usePersistKnowledgeWorkspace()
  const mounts = useVaults()
  const [selectedRootState, setSelectedRootState] = useState<SelectedKnowledgeRoot | null>(null)
  const [uniqueDialogOpen, setUniqueDialogOpen] = useState(false)
  const [activePaneElement, setActivePaneElement] = useState<HTMLElement | null>(null)
  const workspaceRef = useRef<HTMLDivElement>(null)
  const fileTreeRef = useRef<HTMLElement>(null)
  const linksRef = useRef<HTMLDivElement>(null)
  const paneElementsRef = useRef<Record<string, HTMLElement | null>>({})
  const selectedRoot = selectedRootState
    ?? (mounts.data?.[0]
      ? { authority: 'external-vault' as const, id: mounts.data[0].id }
      : { authority: 'overlay' as const, id: 'overlay_space:default' as const })
  const selectedVaultId = selectedRoot.authority === 'external-vault' ? selectedRoot.id : ''
  const files = useVaultFiles(selectedVaultId)
  const activePane = useKnowledgeWorkspaceStore(
    (state) => state.panes[state.activePaneId],
  )
  const activePaneId = useKnowledgeWorkspaceStore((state) => state.activePaneId)
  const activeTab = activePane?.tabs.find(
    (tab) => tab.id === activePane.activeTabId,
  ) ?? activePane?.tabs[0]
  const openTab = useKnowledgeWorkspaceStore((state) => state.openTab)
  const {
    mutateAsync: scanVault,
    isPending: scanPending,
    error: scanError,
  } = useScanVault(
    selectedVaultId,
    activeTab?.sourceAuthority === 'external-vault' && activeTab.vaultId === selectedVaultId
      ? activeTab.noteId
      : undefined,
  )
  const {
    mutateAsync: createTodayOverlay,
    isPending: todayOverlayPending,
    isError: todayOverlayError,
  } = useTodayOverlayNote()

  const openFile = (file: VaultFile, paneId?: string) => {
    openTab(tabFromFile(file), paneId)
  }

  const navigate: KnowledgeNavigate = (
    targetVaultId,
    targetNoteId,
    relativePathHint,
    titleHint,
    paneId,
    targetText,
    sourceAuthority,
  ) => {
    const listedFile = sourceAuthority === 'external-vault'
      ? files.data?.find(
          (file) => file.vault_id === targetVaultId
            && file.note_id === targetNoteId,
        )
      : undefined
    if (listedFile) {
      openTab({
        vaultId: listedFile.vault_id,
        noteId: listedFile.note_id,
        title: titleHint?.trim()
          || targetText
          || titleFromRelativePath(listedFile.relative_path),
        relativePath: listedFile.relative_path,
        sourceAuthority,
      }, paneId)
      return
    }

    const existingTab = Object.values(
      useKnowledgeWorkspaceStore.getState().panes,
    )
      .flatMap((pane) => pane.tabs)
      .find((tab) => tab.vaultId === targetVaultId
        && tab.noteId === targetNoteId
        && tab.sourceAuthority === sourceAuthority)
    if (existingTab) {
      openTab({
        vaultId: existingTab.vaultId,
        noteId: existingTab.noteId,
        title: existingTab.title,
        relativePath: existingTab.relativePath,
        viewMode: existingTab.viewMode,
        sourceAuthority,
      }, paneId)
      return
    }

    if (!relativePathHint) return
    openTab({
      vaultId: targetVaultId,
      noteId: targetNoteId,
      title: titleHint?.trim() || targetText || titleFromRelativePath(relativePathHint),
      relativePath: relativePathHint,
      sourceAuthority,
    }, paneId)
  }

  const selected = selectedRoot.authority === 'external-vault'
    ? mounts.data?.find((mount) => mount.id === selectedRoot.id)
    : undefined
  const selectedNoteId = activeTab?.sourceAuthority === 'external-vault' && activeTab.vaultId === selectedVaultId
    ? activeTab.noteId
    : ''
  const scanSelectedVault = useCallback(
    async () => {
      if (selectedRoot.authority !== 'external-vault') return
      await scanVault()
    },
    [scanVault, selectedRoot.authority],
  )
  const openTodayOverlay = useCallback(async () => {
    const page = await createTodayOverlay(localDateKey())
    openTab(tabFromOverlay(page))
  }, [createTodayOverlay, openTab])
  const openUniqueOverlayDialog = useCallback(() => setUniqueDialogOpen(true), [])

  useEffect(() => {
    setActivePaneElement(paneElementsRef.current[activePaneId] ?? null)
  }, [activePaneId])

  const onPaneElement = useCallback((paneId: string, element: HTMLElement | null) => {
    paneElementsRef.current[paneId] = element
    if (paneId === activePaneId) setActivePaneElement(element)
  }, [activePaneId])

  return (
    <div
      ref={workspaceRef}
      className="flex min-h-0 flex-1 flex-col"
      data-testid="knowledge-workspace"
      tabIndex={-1}
    >
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
          {selectedRoot.authority === 'external-vault' && <Button
            type="button"
            variant="outline"
            onClick={() => { void scanVault().catch(() => undefined) }}
            disabled={scanPending}
          >
            <RefreshCw
              className={`mr-2 h-4 w-4 ${scanPending ? 'animate-spin' : ''}`}
            />
            {t('knowledge.scan')}
          </Button>}
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
          {selectedRoot.authority === 'external-vault' && scanError && (
            <p role="alert" className="text-sm text-destructive">
              {t('knowledge.loadError')}
            </p>
          )}
        </div>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(16rem,22rem)_minmax(0,1fr)_minmax(15rem,20rem)]">
        <aside
          ref={fileTreeRef}
          className="flex min-h-64 flex-col gap-4 border-b p-4 lg:border-b-0 lg:border-r"
          aria-label={t('knowledge.files')}
          tabIndex={-1}
        >
          <label className="text-sm font-medium" htmlFor="vault-mount">
            {t('knowledge.mounts')}
          </label>
          <select
            id="vault-mount"
            value={`${selectedRoot.authority}:${selectedRoot.id}`}
            onChange={(event) => {
              const next = event.target.value
              setSelectedRootState(next === 'overlay:overlay_space:default'
                ? { authority: 'overlay', id: 'overlay_space:default' }
                : { authority: 'external-vault', id: next.replace(/^external-vault:/, '') })
            }}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="overlay:overlay_space:default">{t('knowledge.overlay.name')}</option>
            {mounts.data?.map((mount) => (
              <option key={mount.id} value={`external-vault:${mount.id}`}>
                {mount.name} · {mount.format_mode}
              </option>
            ))}
          </select>
          <OverlayUtilityPanel
            onOpen={openTab}
            onNewUnique={openUniqueOverlayDialog}
            onToday={openTodayOverlay}
            todayPending={todayOverlayPending}
            todayError={todayOverlayError}
          />
          {selectedRoot.authority === 'external-vault' && (mounts.isLoading ? (
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
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{t('knowledge.status')}</span>
                  <Badge variant="outline">{t('knowledge.readOnly')}</Badge>
                </div>
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
          ))}
        </aside>
        <main className="min-h-0 min-w-0 overflow-hidden">
          <KnowledgeWorkspaceLayout
            onPaneElement={onPaneElement}
            renderPane={(pane) => (
              <KnowledgePaneContent
                pane={pane}
                mounts={mounts.data || []}
                onNavigate={navigate}
              />
            )}
          />
        </main>
        <div ref={linksRef} tabIndex={-1}>
          <KnowledgeLinksInspector onNavigate={navigate} />
        </div>
      </div>
      <KnowledgeCommandBridge
        workspaceRef={workspaceRef}
        activePaneElement={activePaneElement}
        fileTreeRef={fileTreeRef}
        linksRef={linksRef}
        selectedVaultId={selectedRoot.authority === 'external-vault' ? selectedRoot.id : null}
        scanSelectedVault={scanSelectedVault}
        openTodayOverlay={openTodayOverlay}
        openUniqueOverlayDialog={openUniqueOverlayDialog}
      />
      <KnowledgeQuickSwitcher mounts={mounts.data || []} />
      <CreateUniqueNoteDialog
        open={uniqueDialogOpen}
        onOpenChange={setUniqueDialogOpen}
        onOpen={openTab}
      />
    </div>
  )
}

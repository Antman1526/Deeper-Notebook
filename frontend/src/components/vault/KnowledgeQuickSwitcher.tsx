'use client'

import { useEffect, useMemo, useState } from 'react'

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import type { VaultMount } from '@/lib/api/vault'
import {
  candidateToOpenTab,
  overlayNotesToKnowledgeCandidates,
  rankKnowledgeCatalog,
} from '@/lib/commands/knowledge-command-catalog'
import { useOverlayNotes } from '@/lib/hooks/use-overlay'
import {
  acknowledgeCommandSurface,
  useCommandSurfaceStore,
} from '@/lib/commands/command-surface-store'
import { useKnowledgeCatalog } from '@/lib/hooks/use-knowledge-command-data'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useKnowledgeWorkspaceStore } from '@/lib/stores/knowledge-workspace-store'

interface KnowledgeQuickSwitcherProps {
  mounts: VaultMount[]
}

export function KnowledgeQuickSwitcher({ mounts }: KnowledgeQuickSwitcherProps) {
  const { t } = useTranslation()
  const surface = useCommandSurfaceStore()
  const {
    requestId: surfaceRequestId,
    kind: surfaceKind,
    initialQuery: surfaceInitialQuery,
    invoker: surfaceInvoker,
  } = surface
  const workspace = useKnowledgeWorkspaceStore()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [invoker, setInvoker] = useState<HTMLElement | null>(null)
  const openTabs = useMemo(
    () => Object.values(workspace.panes).flatMap(pane => pane.tabs),
    [workspace.panes],
  )
  const catalog = useKnowledgeCatalog(mounts, openTabs, open)
  const overlay = useOverlayNotes()
  const allCandidates = useMemo(
    () => [...catalog.candidates, ...overlayNotesToKnowledgeCandidates(overlay.data || [], openTabs)],
    [catalog.candidates, openTabs, overlay.data],
  )
  const candidates = useMemo(
    () => rankKnowledgeCatalog(allCandidates, query, 50),
    [allCandidates, query],
  )
  const showLoadingPlaceholder = catalog.isLoading && candidates.length === 0

  useEffect(() => {
    if (surfaceKind !== 'quick-switcher') return
    setQuery(surfaceInitialQuery)
    setInvoker(surfaceInvoker)
    setOpen(true)
    acknowledgeCommandSurface(surfaceRequestId)
  }, [surfaceInitialQuery, surfaceInvoker, surfaceKind, surfaceRequestId])

  const statusMessage = catalog.isLoading
    ? t('knowledge.filesLoading')
    : catalog.failedVaultCount > 0
      ? t('knowledge.partialCatalogFailure', { count: catalog.failedVaultCount })
      : candidates.length === 0
        ? t('knowledge.noMatchingFiles')
        : ''

  const close = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (nextOpen) return
    requestAnimationFrame(() => {
      if (invoker?.isConnected) invoker.focus()
    })
  }

  const selectCandidate = (candidate: (typeof candidates)[number]) => {
    workspace.openTab(candidateToOpenTab(candidate))
    close(false)
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={close}
      title={t('knowledge.quickSwitcher')}
      description={t('knowledge.quickSwitcherDescription')}
      className="sm:max-w-2xl"
    >
      <CommandInput
        aria-label={t('knowledge.quickSwitcher')}
        value={query}
        onValueChange={setQuery}
        autoComplete="off"
      />
      <p
        role="status"
        aria-live="polite"
        className={catalog.isLoading && candidates.length > 0
          ? 'border-b px-3 py-2 text-sm text-muted-foreground'
          : 'sr-only'}
      >
        {statusMessage}
      </p>
      {catalog.failedVaultCount > 0 && (
        <div className="flex items-center justify-between gap-3 border-b px-3 py-2 text-sm text-muted-foreground">
          <span>{t('knowledge.partialCatalogFailure', { count: catalog.failedVaultCount })}</span>
          <button
            type="button"
            className="font-medium text-foreground underline-offset-4 hover:underline"
            onClick={() => void catalog.retryFailedVaults()}
          >
            {t('common.retry')}
          </button>
        </div>
      )}
      <CommandList>
        {showLoadingPlaceholder ? (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">
            {t('knowledge.filesLoading')}
          </p>
        ) : (
          <>
            <CommandEmpty>{t('knowledge.noMatchingFiles')}</CommandEmpty>
            <CommandGroup>
              {candidates.map(candidate => (
                <CommandItem
                  key={candidate.key}
                  value={`${candidate.title} ${candidate.relativePath} ${candidate.vaultName}`}
                  onClick={() => selectCandidate(candidate)}
                  onSelect={() => selectCandidate(candidate)}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{candidate.title}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {candidate.relativePath} · {candidate.vaultName}
                    </span>
                  </span>
                  {candidate.isOpen && (
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {t('knowledge.alreadyOpen')}
                    </span>
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  )
}

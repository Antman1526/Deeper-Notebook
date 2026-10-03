'use client'

import { useEffect, useRef, useState } from 'react'
import { Bookmark, CalendarDays, Dices, FolderKanban, PanelLeftClose, PanelLeftOpen } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { KnowledgeWorkspaceNavigation } from '@/lib/api/knowledge-workspace'
import { useTranslation } from '@/lib/hooks/use-translation'

type UtilityMode = KnowledgeWorkspaceNavigation['utilityMode']

interface KnowledgeUtilityRailProps {
  mode: UtilityMode
  sidebarVisible: boolean
  canBookmarkCurrent: boolean
  randomPending?: boolean
  drawerCloseLabel?: string
  onCloseDrawer?: () => void
  onNavigationChange: (change: Partial<KnowledgeWorkspaceNavigation>) => void
  onToday: () => void
  onRandomNote: () => void
  onBookmarkCurrent: () => void
}

export function KnowledgeUtilityRail({
  mode,
  sidebarVisible,
  canBookmarkCurrent,
  randomPending = false,
  drawerCloseLabel,
  onCloseDrawer,
  onNavigationChange,
  onToday,
  onRandomNote,
  onBookmarkCurrent,
}: KnowledgeUtilityRailProps) {
  const { t } = useTranslation()
  const [displayMode, setDisplayMode] = useState(mode)
  const pointerFocusRef = useRef<HTMLElement | null>(null)
  const collapseButtonRef = useRef<HTMLButtonElement>(null)
  useEffect(() => setDisplayMode(mode), [mode])
  useEffect(() => {
    if (!sidebarVisible) collapseButtonRef.current?.focus()
  }, [sidebarVisible])
  const selectMode = (utilityMode: UtilityMode) => {
    setDisplayMode(utilityMode)
    onNavigationChange({ utilityMode })
    const focus = pointerFocusRef.current
    pointerFocusRef.current = null
    if (focus?.isConnected) requestAnimationFrame(() => focus.focus())
  }
  const capturePointerFocus = () => { pointerFocusRef.current = document.activeElement as HTMLElement | null }
  const modes: Array<{ id: UtilityMode; label: string }> = [
    { id: 'sources', label: t('knowledge.navigation.sources') },
    { id: 'bookmarks', label: t('knowledge.navigation.bookmarks') },
    { id: 'workspaces', label: t('knowledge.navigation.workspaces') },
  ]

  if (!sidebarVisible) {
    return (
      <nav aria-label={t('knowledge.knowledgeUtilityRail.utilities')} className="flex items-center justify-between p-2">
        {onCloseDrawer && drawerCloseLabel ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            aria-label={drawerCloseLabel}
            onClick={onCloseDrawer}
            className="research-core-drawer-close"
          >
            {drawerCloseLabel}
          </Button>
        ) : <span />}
        <Button
          ref={collapseButtonRef}
          type="button"
          size="icon"
          variant="ghost"
          aria-label={t('knowledge.knowledgeUtilityRail.restoreSidebar')}
          onClick={() => onNavigationChange({ sidebarVisible: true })}
        >
          <PanelLeftOpen aria-hidden="true" className="h-4 w-4" />
        </Button>
      </nav>
    )
  }

  return (
    <nav aria-label={displayMode === 'bookmarks' ? t('knowledge.navigation.bookmarks') : t('knowledge.knowledgeUtilityRail.utilities')} className="space-y-3">
      {onCloseDrawer && drawerCloseLabel ? (
        <div className="flex items-center justify-end">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            aria-label={drawerCloseLabel}
            onClick={onCloseDrawer}
            className="research-core-drawer-close"
          >
            {drawerCloseLabel}
          </Button>
        </div>
      ) : null}
      <div className="grid grid-cols-2 gap-2">
        <Button type="button" size="sm" variant="outline" className="h-auto min-h-11 min-w-0 shrink whitespace-normal py-2 leading-tight hyphens-auto wrap-anywhere" onClick={onToday}>
          <CalendarDays aria-hidden="true" className="h-4 w-4" />
          {t('knowledge.knowledgeUtilityRail.today')}
        </Button>
        <Button type="button" size="sm" variant="outline" className="h-auto min-h-11 min-w-0 shrink whitespace-normal py-2 leading-tight hyphens-auto wrap-anywhere" onPointerDown={capturePointerFocus} onClick={() => selectMode('bookmarks')}>
          <Bookmark aria-hidden="true" className="h-4 w-4" />
          {t('knowledge.navigation.bookmarks')}
        </Button>
        <Button type="button" size="sm" variant="outline" className="h-auto min-h-11 min-w-0 shrink whitespace-normal py-2 leading-tight hyphens-auto wrap-anywhere" onClick={onRandomNote} disabled={randomPending}>
          <Dices aria-hidden="true" className="h-4 w-4" />
          {t('knowledge.knowledgeUtilityRail.randomNote')}
        </Button>
        <Button type="button" size="sm" variant="outline" className="h-auto min-h-11 min-w-0 shrink whitespace-normal py-2 leading-tight hyphens-auto wrap-anywhere" onPointerDown={capturePointerFocus} onClick={() => selectMode('workspaces')}>
          <FolderKanban aria-hidden="true" className="h-4 w-4" />
          {t('knowledge.navigation.workspaces')}
        </Button>
      </div>
      <div role="tablist" aria-label={t('knowledge.knowledgeUtilityRail.modeLabel')} className="flex rounded-md border p-1">
        {modes.map(({ id, label }) => (
          <Button
            key={id}
            type="button"
            role="tab"
            size="sm"
            variant={displayMode === id ? 'secondary' : 'ghost'}
            aria-selected={displayMode === id}
            onPointerDown={capturePointerFocus}
            onClick={() => selectMode(id)}
            className="h-auto min-h-11 min-w-0 flex-1 whitespace-normal px-1 py-2 leading-tight hyphens-auto wrap-anywhere"
          >
            {label}
          </Button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onBookmarkCurrent}
          disabled={!canBookmarkCurrent}
          className="h-auto min-h-11 min-w-0 shrink whitespace-normal py-2 leading-tight hyphens-auto wrap-anywhere"
        >
          <Bookmark aria-hidden="true" className="h-4 w-4" />
          {t('knowledge.knowledgeUtilityRail.bookmarkCurrentTarget')}
        </Button>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          aria-label={sidebarVisible ? t('knowledge.knowledgeUtilityRail.collapseSidebar') : t('knowledge.knowledgeUtilityRail.restoreSidebar')}
          ref={collapseButtonRef}
          onClick={() => onNavigationChange({ sidebarVisible: false })}
        >
          {sidebarVisible ? <PanelLeftClose aria-hidden="true" className="h-4 w-4" /> : <PanelLeftOpen aria-hidden="true" className="h-4 w-4" />}
        </Button>
      </div>
      {!canBookmarkCurrent && (
        <p className="text-xs text-muted-foreground">
          {t('knowledge.knowledgeUtilityRail.noDocumentId')}
        </p>
      )}
    </nav>
  )
}

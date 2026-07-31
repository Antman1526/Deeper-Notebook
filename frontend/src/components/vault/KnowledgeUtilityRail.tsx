'use client'

import { useEffect, useState } from 'react'
import { Bookmark, CalendarDays, Dices, FolderKanban, PanelLeftClose, PanelLeftOpen } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { KnowledgeWorkspaceNavigation } from '@/lib/api/knowledge-workspace'

type UtilityMode = KnowledgeWorkspaceNavigation['utilityMode']

interface KnowledgeUtilityRailProps {
  mode: UtilityMode
  sidebarVisible: boolean
  canBookmarkCurrent: boolean
  randomPending?: boolean
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
  onNavigationChange,
  onToday,
  onRandomNote,
  onBookmarkCurrent,
}: KnowledgeUtilityRailProps) {
  const [displayMode, setDisplayMode] = useState(mode)
  useEffect(() => setDisplayMode(mode), [mode])
  const selectMode = (utilityMode: UtilityMode) => {
    setDisplayMode(utilityMode)
    onNavigationChange({ utilityMode })
  }
  const modes: Array<{ id: UtilityMode; label: string }> = [
    { id: 'sources', label: 'Sources' },
    { id: 'bookmarks', label: 'Bookmarks' },
    { id: 'workspaces', label: 'Workspaces' },
  ]

  return (
    <nav aria-label={displayMode === 'bookmarks' ? 'Bookmarks' : 'Knowledge utilities'} className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Button type="button" size="sm" variant="outline" onClick={onToday}>
          <CalendarDays aria-hidden="true" className="mr-1.5 h-4 w-4" />
          Today
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => selectMode('bookmarks')}>
          <Bookmark aria-hidden="true" className="mr-1.5 h-4 w-4" />
          Bookmarks
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onRandomNote} disabled={randomPending}>
          <Dices aria-hidden="true" className="mr-1.5 h-4 w-4" />
          Random Note
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => selectMode('workspaces')}>
          <FolderKanban aria-hidden="true" className="mr-1.5 h-4 w-4" />
          Workspaces
        </Button>
      </div>
      <div role="tablist" aria-label="Knowledge utility mode" className="flex rounded-md border p-1">
        {modes.map(({ id, label }) => (
          <Button
            key={id}
            type="button"
            role="tab"
            size="sm"
            variant={displayMode === id ? 'secondary' : 'ghost'}
            aria-selected={displayMode === id}
            onClick={() => selectMode(id)}
            className="min-w-0 flex-1"
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
        >
          <Bookmark aria-hidden="true" className="mr-1.5 h-4 w-4" />
          Bookmark Current Target
        </Button>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          aria-label={sidebarVisible ? 'Collapse utility sidebar' : 'Restore utility sidebar'}
          onClick={() => onNavigationChange({ sidebarVisible: !sidebarVisible })}
        >
          {sidebarVisible ? <PanelLeftClose aria-hidden="true" className="h-4 w-4" /> : <PanelLeftOpen aria-hidden="true" className="h-4 w-4" />}
        </Button>
      </div>
      {!canBookmarkCurrent && (
        <p className="text-xs text-muted-foreground">
          The active page has no unified document ID.
        </p>
      )}
    </nav>
  )
}

'use client'

import { NotebookResponse } from '@/lib/types/api'
import { NotebookCard } from './NotebookCard'
import { NotebookRow } from './NotebookRow'
import { useNotebookViewStore } from '@/lib/stores/notebook-view-store'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/EmptyState'
import { Book, ChevronDown, ChevronRight, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useState } from 'react'
import { useTranslation } from '@/lib/hooks/use-translation'

interface NotebookListProps {
  notebooks?: NotebookResponse[]
  isLoading: boolean
  title: string
  collapsible?: boolean
  emptyTitle?: string
  emptyDescription?: string
  onAction?: () => void
  actionLabel?: string
  // v0.8.80 — extra empty-state action (e.g. "Explore a sample notebook"),
  // rendered below the primary action button.
  extraAction?: React.ReactNode
}

export function NotebookList({
  notebooks,
  isLoading,
  title,
  collapsible = false,
  emptyTitle,
  emptyDescription,
  onAction,
  actionLabel,
  extraAction,
}: NotebookListProps) {
  const { t } = useTranslation()
  const viewMode = useNotebookViewStore((state) => state.viewMode)
  const [isExpanded, setIsExpanded] = useState(!collapsible)

  if (isLoading) {
    // v0.8.70 — skeleton cards instead of a centered spinner: the layout
    // settles instantly (no jump when data lands) and reads as faster.
    return (
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 2xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="space-y-3 rounded-lg border bg-card p-4">
            <div className="flex items-center gap-3">
              <Skeleton className="h-9 w-9 rounded-md" />
              <Skeleton className="h-4 w-2/3" />
            </div>
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-4/5" />
            <Skeleton className="h-3 w-1/3" />
          </div>
        ))}
      </div>
    )
  }

  if (!notebooks || notebooks.length === 0) {
    return (
      <EmptyState
        icon={Book}
        title={emptyTitle ?? t('common.noResults')}
        description={emptyDescription ?? t('chat.startByCreating')}
        action={(onAction && actionLabel) || extraAction ? (
          <div className="mt-4 flex flex-col items-center gap-2">
            {onAction && actionLabel && (
              <Button onClick={onAction} variant="outline">
                <Plus className="h-4 w-4 mr-2" />
                {actionLabel}
              </Button>
            )}
            {extraAction}
          </div>
        ) : undefined}
      />
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {collapsible && (
          <Button
            variant="ghost"
            size="sm"
            aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${title}`}
            onClick={() => setIsExpanded(!isExpanded)}
          >
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </Button>
        )}
        <h2 className="text-lg font-semibold">{title}</h2>
        <span className="text-sm text-muted-foreground">({notebooks.length})</span>
      </div>

      {isExpanded && (
        viewMode === 'list' ? (
          <div className="flex flex-col gap-2">
            {notebooks.map((notebook) => (
              <NotebookRow key={notebook.id} notebook={notebook} />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 2xl:grid-cols-3">
            {notebooks.map((notebook) => (
              <NotebookCard key={notebook.id} notebook={notebook} />
            ))}
          </div>
        )
      )}
    </div>
  )
}

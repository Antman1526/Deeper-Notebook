'use client'

import { LayoutGrid, List } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useNotebookViewStore } from '@/lib/stores/notebook-view-store'

/**
 * v0.8.130 — switches the notebooks page between the tile grid and the list. The
 * preference was already stored (`notebook-view-store`) and the list view already
 * existed, but nothing in the UI could change it, so the list was unreachable.
 */
export function NotebookViewToggle() {
  const { t } = useTranslation()
  const viewMode = useNotebookViewStore((state) => state.viewMode)
  const setViewMode = useNotebookViewStore((state) => state.setViewMode)

  const options = [
    { mode: 'tile' as const, label: t('notebooks.viewGrid'), Icon: LayoutGrid },
    { mode: 'list' as const, label: t('notebooks.viewList'), Icon: List },
  ]

  return (
    <div role="group" aria-label={t('notebooks.viewToggle')} className="inline-flex items-center gap-1">
      {options.map(({ mode, label, Icon }) => (
        <Button
          key={mode}
          type="button"
          size="sm"
          variant={viewMode === mode ? 'secondary' : 'outline'}
          aria-pressed={viewMode === mode}
          aria-label={label}
          title={label}
          onClick={() => setViewMode(mode)}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </Button>
      ))}
    </div>
  )
}

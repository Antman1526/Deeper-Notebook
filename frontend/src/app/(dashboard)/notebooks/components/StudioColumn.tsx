'use client'

import { useMemo } from 'react'
import { Sparkles } from 'lucide-react'

import { ArtifactRail } from '@/components/deeper-notebook'
import { CollapsibleColumn, createCollapseButton } from '@/components/notebooks/CollapsibleColumn'
import { ResearchRunWorkspace } from '@/components/research/ResearchRunWorkspace'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'
import type { SourceListResponse } from '@/lib/types/api'

interface StudioColumnProps {
  notebookId: string
  sources: SourceListResponse[] | undefined
  sourcesLoading: boolean
}

// v0.8.130 — Phase 2a: Guided research and the Evidence Studio band used to stack
// above the panes, pushing them ~1,000px down the page. They now live in their own
// collapsible column beside Notes; Phase 2b restyles the contents as a tile grid.
export function StudioColumn({ notebookId, sources, sourcesLoading }: StudioColumnProps) {
  const { t } = useTranslation()
  const studioLabel = t('notebooks.studio')
  const { studioCollapsed, toggleStudio } = useNotebookColumnsStore()
  const collapseButton = useMemo(
    () => createCollapseButton(toggleStudio, studioLabel),
    [toggleStudio, studioLabel],
  )

  return (
    <CollapsibleColumn
      isCollapsed={studioCollapsed}
      onToggle={toggleStudio}
      collapsedIcon={Sparkles}
      collapsedLabel={studioLabel}
    >
      <section aria-label={studioLabel} className="h-full min-h-0">
        <Card data-dn-column="" className="flex h-full flex-1 flex-col overflow-hidden">
          <CardHeader className="flex-shrink-0">
            <div className="flex items-center gap-1">
              <CardTitle className="min-w-0 flex-1 truncate text-base font-medium">{studioLabel}</CardTitle>
              {collapseButton}
            </div>
          </CardHeader>
          {/* v0.8.130 — a size container: the Evidence Studio band and Guided research lay
              out by the column's width, not the window's. */}
          <CardContent className="@container min-h-0 flex-1 overflow-y-auto">
            {/* v0.8.130 — Phase 2b: generators first; Guided research follows. */}
            <ArtifactRail notebookId={notebookId} sources={sources} sourcesLoading={sourcesLoading} />
            <ResearchRunWorkspace notebookId={notebookId} />
          </CardContent>
        </Card>
      </section>
    </CollapsibleColumn>
  )
}

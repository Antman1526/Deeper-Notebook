'use client'

import { AppShell } from '@/components/layout/AppShell'
import { RecentSourceStrip } from '@/components/deeper-notebook/source-gallery/RecentSourceStrip'
import { KnowledgeExplorer } from '@/components/vault/KnowledgeExplorer'
import { isVisualSystemV2Enabled } from '@/lib/features'
import { useSourceVisualsEnabled } from '@/lib/features-client'
import { useRecentVisualSources } from '@/lib/hooks/use-source-visuals'

export default function KnowledgePage() {
  const recentSources = useRecentVisualSources(4)
  const sourceVisualsEnabled = useSourceVisualsEnabled()
  const visualGalleryEnabled = isVisualSystemV2Enabled() && sourceVisualsEnabled

  return (
    <AppShell>
      <div className="min-w-0 space-y-6">
        {visualGalleryEnabled ? (
          <div
            className="min-h-[15rem] min-w-0 sm:min-h-[12rem]"
            data-dn-recent-source-slot="true"
          >
            <RecentSourceStrip sources={recentSources.data ?? []} />
          </div>
        ) : null}
        <KnowledgeExplorer />
      </div>
    </AppShell>
  )
}

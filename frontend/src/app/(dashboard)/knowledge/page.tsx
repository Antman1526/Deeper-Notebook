'use client'

import { AppShell } from '@/components/layout/AppShell'
import { RecentSourceStrip } from '@/components/deeper-notebook/source-gallery/RecentSourceStrip'
import { KnowledgeExplorer } from '@/components/vault/KnowledgeExplorer'
import { isSourceVisualsEnabled, isVisualSystemV2Enabled } from '@/lib/features'
import { useRecentVisualSources } from '@/lib/hooks/use-source-visuals'

export default function KnowledgePage() {
  const recentSources = useRecentVisualSources(4)
  const visualGalleryEnabled = isVisualSystemV2Enabled() && isSourceVisualsEnabled()

  return (
    <AppShell>
      <div className="min-w-0 space-y-6">
        {visualGalleryEnabled ? <RecentSourceStrip sources={recentSources.data ?? []} /> : null}
        <KnowledgeExplorer />
      </div>
    </AppShell>
  )
}

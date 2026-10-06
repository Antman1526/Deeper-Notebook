'use client'

import { RecentSourceStrip } from '@/components/deeper-notebook/source-gallery/RecentSourceStrip'
import { KnowledgeExplorer } from '@/components/vault/KnowledgeExplorer'
import { isVisualSystemV2Enabled } from '@/lib/features'
import { useSourceVisualsEnabled } from '@/lib/features-client'
import { useRecentVisualSources } from '@/lib/hooks/use-source-visuals'
import { useTranslation } from '@/lib/hooks/use-translation'

export default function KnowledgePage() {
  const recentSources = useRecentVisualSources(4)
  const sourceVisualsEnabled = useSourceVisualsEnabled()
  const visualGalleryEnabled = isVisualSystemV2Enabled() && sourceVisualsEnabled
  // v0.8.130 — the slot's height is reserved so the strip does not push the page down
  // when it loads. Once the answer is "no recent sources" there is nothing to wait
  // for, and the reserved height was a blank band above the page for good.
  const noRecentSources = recentSources.isSuccess === true && (recentSources.data?.length ?? 0) === 0
  const { t } = useTranslation()

  return (
    <>
      {/* v0.8.130 — Phase 4b: the page's main landmark (other routes get one from WorkspacePage). */}
      <main aria-label={t('navigation.knowledge')} className="min-w-0 space-y-6">
        {visualGalleryEnabled && !noRecentSources ? (
          <div
            className="min-h-[15rem] min-w-0 sm:min-h-[12rem]"
            data-dn-recent-source-slot="true"
          >
            <RecentSourceStrip sources={recentSources.data ?? []} />
          </div>
        ) : null}
        <KnowledgeExplorer />
      </main>
    </>
  )
}

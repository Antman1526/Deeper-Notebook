import type { ReactNode } from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'

export interface PodcastStudioFolioProps {
  researchSet: ReactNode
  editorialBrief: ReactNode
  storyboard: ReactNode
  modelPlan: ReactNode
  production: ReactNode
  review: ReactNode
}

/** Presentation-only production spread; PodcastStudio retains all state and actions. */
export function PodcastStudioFolio({
  researchSet,
  editorialBrief,
  storyboard,
  modelPlan,
  production,
  review,
}: PodcastStudioFolioProps) {
  const { t } = useTranslation()
  return (
    <section aria-label={t('podcasts.podcastStudioFolio.productionFolio')} data-dn-folio-page data-studio-layout>
      <div data-dn-folio-spread>
        <section aria-label={t('podcasts.podcastStudioFolio.researchSet')} data-dn-folio-primary>{researchSet}</section>
        <section aria-label={t('podcasts.podcastStudioFolio.editorialBrief')} data-dn-folio-secondary>{editorialBrief}</section>
      </div>
      <div data-dn-folio-spread>
        <section aria-label={t('podcasts.podcastStudioFolio.outlineStoryboard')} data-dn-folio-primary>{storyboard}</section>
        <section aria-label={t('podcasts.podcastStudioFolio.modelPlan')} data-dn-folio-secondary>{modelPlan}</section>
      </div>
      <section aria-label={t('podcasts.podcastStudioFolio.productionGate')} data-dn-folio-primary>{production}</section>
      <aside aria-label={t('podcasts.podcastStudioFolio.productionReview')} data-dn-folio-margin-note>{review}</aside>
    </section>
  )
}

import type { ReactNode } from 'react'

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
  return (
    <section aria-label="Podcast production folio" data-dn-folio-page data-studio-layout>
      <div data-dn-folio-spread>
        <section aria-label="Research set" data-dn-folio-primary>{researchSet}</section>
        <section aria-label="Editorial brief" data-dn-folio-secondary>{editorialBrief}</section>
      </div>
      <div data-dn-folio-spread>
        <section aria-label="Outline storyboard" data-dn-folio-primary>{storyboard}</section>
        <section aria-label="Model plan" data-dn-folio-secondary>{modelPlan}</section>
      </div>
      <section aria-label="Production gate" data-dn-folio-primary>{production}</section>
      <aside aria-label="Production review" data-dn-folio-margin-note>{review}</aside>
    </section>
  )
}

import type { ReactNode } from 'react'

import { isLuminousFolioEnabled } from '@/lib/features'

export interface EvidenceStudioFolioProps {
  sourceDesk: ReactNode
  editorialBrief: ReactNode
  artifactPages: ReactNode
  trustMargin?: ReactNode
  status?: ReactNode
}

/** A view-only working spread; the page retains every mutation and handler. */
export function EvidenceStudioFolio({
  sourceDesk,
  editorialBrief,
  artifactPages,
  trustMargin,
  status,
}: EvidenceStudioFolioProps) {
  const Landmark = isLuminousFolioEnabled() ? 'main' : 'section'

  return (
    <Landmark aria-label="Evidence Studio folio" data-dn-folio-page>
      {status ? <div data-dn-folio-margin-note>{status}</div> : null}
      <div data-dn-folio-spread>
        <section aria-label="Source desk" data-dn-folio-primary>{sourceDesk}</section>
        <section aria-label="Editorial brief" data-dn-folio-secondary>{editorialBrief}</section>
      </div>
      <div data-dn-folio-primary>
        <section aria-label="Artifact pages">{artifactPages}</section>
      </div>
      {trustMargin ? <aside aria-label="Trust margin" data-dn-folio-margin-note>{trustMargin}</aside> : null}
    </Landmark>
  )
}

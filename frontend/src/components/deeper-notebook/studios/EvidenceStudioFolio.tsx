import type { ReactNode } from 'react'

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
  return (
    <main aria-label="Evidence Studio folio" data-dn-folio-page>
      {status ? <div data-dn-folio-margin-note>{status}</div> : null}
      {/* v0.8.98 — `evidence-studio` widens only THIS spread's secondary column.
          The shared 15rem minimum clamped the "Pick output mode" rail to 240px;
          after card padding the mode descriptions wrapped to one or two words a
          line. Scoped so the podcast studio and graph atlas spreads, which hold
          narrower content, keep the original ratio. See folio.css. */}
      <div data-dn-folio-spread data-dn-folio-variant="evidence-studio">
        <section aria-label="Source desk" data-dn-folio-primary>{sourceDesk}</section>
        <section aria-label="Editorial brief" data-dn-folio-secondary>{editorialBrief}</section>
      </div>
      <div data-dn-folio-primary>
        <section aria-label="Artifact pages">{artifactPages}</section>
      </div>
      {trustMargin ? <aside aria-label="Trust margin" data-dn-folio-margin-note>{trustMargin}</aside> : null}
    </main>
  )
}

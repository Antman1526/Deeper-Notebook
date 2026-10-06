import type { ReactNode } from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'

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
  const { t } = useTranslation()
  return (
    <main aria-label={t('workspace.evidenceStudioFolio.ariaLabel')} data-dn-folio-page>
      {/* v0.8.130 — Phase 3a: data-dn-studio-header lets V2 drop the margin-note panel
          from the page header (it read as a heavy tinted block). */}
      {status ? <div data-dn-folio-margin-note data-dn-studio-header>{status}</div> : null}
      {/* v0.8.98 — `evidence-studio` widens only THIS spread's secondary column.
          The shared 15rem minimum clamped the "Pick output mode" rail to 240px;
          after card padding the mode descriptions wrapped to one or two words a
          line. Scoped so the podcast studio and graph atlas spreads, which hold
          narrower content, keep the original ratio. See folio.css. */}
      <div data-dn-folio-spread data-dn-folio-variant="evidence-studio">
        <section aria-label={t('workspace.evidenceStudioFolio.sourceDesk')} data-dn-folio-primary>{sourceDesk}</section>
        <section aria-label={t('workspace.evidenceStudioFolio.editorialBrief')} data-dn-folio-secondary>{editorialBrief}</section>
      </div>
      <div data-dn-folio-primary>
        <section aria-label={t('workspace.evidenceStudioFolio.artifactPages')}>{artifactPages}</section>
      </div>
      {trustMargin ? <aside aria-label={t('workspace.evidenceStudioFolio.trustMargin')} data-dn-folio-margin-note>{trustMargin}</aside> : null}
    </main>
  )
}

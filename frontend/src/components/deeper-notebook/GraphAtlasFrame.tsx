import type { ReactNode } from 'react'

export interface GraphAtlasFrameProps {
  actions?: ReactNode
  legend: ReactNode
  canvas: ReactNode
  inspector?: ReactNode
}

/** Presentation-only atlas frame; graph state and navigation stay with VaultGraph. */
export function GraphAtlasFrame({
  actions,
  legend,
  canvas,
  inspector,
}: GraphAtlasFrameProps) {
  return (
    <section aria-label="Connection atlas" data-dn-folio-page>
      <header data-dn-folio-evidence-header>
        <div>
          <p data-dn-folio-page-eyebrow>Knowledge connections</p>
          <h2 data-dn-folio-page-title>Connection atlas</h2>
        </div>
        {actions ? <div data-dn-folio-state-action>{actions}</div> : null}
      </header>
      <div data-dn-folio-spread>
        <div data-dn-folio-primary>{canvas}</div>
        <aside aria-label="Graph context" data-dn-folio-secondary>
          <div aria-label="Graph legend" data-dn-folio-margin-note>{legend}</div>
          {inspector ? <div aria-label="Graph inspector" data-dn-folio-margin-note>{inspector}</div> : null}
        </aside>
      </div>
    </section>
  )
}

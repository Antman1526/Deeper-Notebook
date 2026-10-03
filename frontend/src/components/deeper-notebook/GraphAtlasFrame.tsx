'use client'

import type { ReactNode } from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'

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
  const { t } = useTranslation()
  return (
    <section aria-label={t('workspace.graphAtlasFrame.title')} data-dn-folio-page>
      <header data-dn-folio-evidence-header>
        <div>
          <p data-dn-folio-page-eyebrow>{t('workspace.graphAtlasFrame.eyebrow')}</p>
          <h2 data-dn-folio-page-title>{t('workspace.graphAtlasFrame.title')}</h2>
        </div>
        {actions ? <div data-dn-folio-state-action>{actions}</div> : null}
      </header>
      <div data-dn-folio-spread>
        <div data-dn-folio-primary>{canvas}</div>
        <aside aria-label={t('workspace.graphAtlasFrame.context')} data-dn-folio-secondary>
          <div aria-label={t('workspace.graphAtlasFrame.legend')} data-dn-folio-margin-note>{legend}</div>
          {inspector ? <div aria-label={t('workspace.graphAtlasFrame.inspector')} data-dn-folio-margin-note>{inspector}</div> : null}
        </aside>
      </div>
    </section>
  )
}

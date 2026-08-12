import * as React from 'react'

import { FolioPage } from './FolioPage'

export interface FolioRouteFrameProps {
  section: string
  title: string
  description?: string
  actions?: React.ReactNode
  context?: React.ReactNode
  children: React.ReactNode
}

/** Route-level composition that gives every folio surface the same frame. */
export const FolioRouteFrame = React.forwardRef<HTMLElement, FolioRouteFrameProps>(
  function FolioRouteFrame(
    { section, title, description, actions, context, children },
    ref,
  ) {
    return (
      <FolioPage
        ref={ref}
        as="main"
        eyebrow={section}
        title={title}
        subtitle={description}
        actions={actions}
        margin={context}
        data-dn-folio-route-frame="true"
      >
        {children}
      </FolioPage>
    )
  },
)

FolioRouteFrame.displayName = 'FolioRouteFrame'

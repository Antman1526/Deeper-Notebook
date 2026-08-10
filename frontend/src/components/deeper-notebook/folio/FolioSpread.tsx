import * as React from 'react'

import { cn } from '@/lib/utils'

export interface FolioSpreadProps extends React.HTMLAttributes<HTMLDivElement> {
  primary: React.ReactNode
  secondary?: React.ReactNode
  secondaryLabel?: string
}

/** A responsive two-column reading surface with an optional context lens. */
export const FolioSpread = React.forwardRef<HTMLDivElement, FolioSpreadProps>(
  function FolioSpread(
    { primary, secondary, secondaryLabel = 'Context lens', className, ...rest },
    ref,
  ) {
    return (
      <div
        {...rest}
        ref={ref}
        data-dn-folio-spread="true"
        className={cn('dn-folio-spread', className)}
      >
        <div data-dn-folio-primary="true" className="dn-folio-primary">
          {primary}
        </div>
        {secondary ? (
          <aside
            aria-label={secondaryLabel}
            data-dn-folio-secondary="true"
            className="dn-folio-secondary"
          >
            {secondary}
          </aside>
        ) : null}
      </div>
    )
  },
)

FolioSpread.displayName = 'FolioSpread'

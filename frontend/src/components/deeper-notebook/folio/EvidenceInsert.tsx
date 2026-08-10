import * as React from 'react'

import { cn } from '@/lib/utils'

export interface EvidenceInsertProps
  extends Omit<React.HTMLAttributes<HTMLElement>, 'children'> {
  label: string
  receipt?: React.ReactNode
  children?: React.ReactNode
}

/**
 * An evidence insert keeps a receipt/action in its own block. It deliberately
 * uses a heading rather than a label element so receipt controls can never be
 * accidentally nested in a form label.
 */
export const EvidenceInsert = React.forwardRef<HTMLElement, EvidenceInsertProps>(
  function EvidenceInsert({ label, receipt, children, className, ...rest }, ref) {
    const generatedId = React.useId()
    const headingId = `${generatedId}-label`

    return (
      <aside
        {...rest}
        ref={ref}
        aria-labelledby={headingId}
        data-dn-folio-evidence="true"
        className={cn('dn-folio-evidence', className)}
      >
        <div data-dn-folio-evidence-header="true" className="dn-folio-evidence-header">
          <h2 id={headingId} data-dn-folio-evidence-label="true">
            {label}
          </h2>
          {receipt ? (
            <div
              data-dn-folio-evidence-receipt="true"
              className="dn-folio-evidence-receipt"
            >
              {receipt}
            </div>
          ) : null}
        </div>
        {children ? (
          <div data-dn-folio-evidence-content="true" className="dn-folio-evidence-content">
            {children}
          </div>
        ) : null}
      </aside>
    )
  },
)

EvidenceInsert.displayName = 'EvidenceInsert'

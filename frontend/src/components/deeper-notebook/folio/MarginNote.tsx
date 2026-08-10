import * as React from 'react'

import { cn } from '@/lib/utils'

export interface MarginNoteProps
  extends Omit<React.HTMLAttributes<HTMLElement>, 'children'> {
  children: React.ReactNode
  label?: string
}

/** A non-blocking margin for context, commentary, backlinks, or review notes. */
export const MarginNote = React.forwardRef<HTMLElement, MarginNoteProps>(
  function MarginNote({ children, label = 'Margin note', className, ...rest }, ref) {
    return (
      <aside
        {...rest}
        ref={ref}
        aria-label={label}
        data-dn-folio-margin-note="true"
        className={cn('dn-folio-margin-note', className)}
      >
        {children}
      </aside>
    )
  },
)

MarginNote.displayName = 'MarginNote'

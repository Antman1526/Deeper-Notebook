import * as React from 'react'

import { cn } from '@/lib/utils'

export interface VisualCardGridProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
  minimum?: 'compact' | 'standard' | 'wide'
}

/** Container-query grid that lets cards reflow without a fixed page width. */
export const VisualCardGrid = React.forwardRef<HTMLDivElement, VisualCardGridProps>(
  function VisualCardGrid({ children, minimum = 'standard', className, ...rest }, ref) {
    return (
      <div
        {...rest}
        ref={ref}
        data-dn-visual-card-grid="true"
        data-dn-visual-card-grid-minimum={minimum}
        className={cn('dn-visual-card-grid', `dn-visual-card-grid-${minimum}`, className)}
      >
        {children}
      </div>
    )
  },
)

VisualCardGrid.displayName = 'VisualCardGrid'

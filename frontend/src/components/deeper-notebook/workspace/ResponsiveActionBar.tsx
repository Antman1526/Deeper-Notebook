import * as React from 'react'

import { cn } from '@/lib/utils'

export interface ResponsiveActionBarProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

/** A single wrapping action row; callers own action order and behavior. */
export const ResponsiveActionBar = React.forwardRef<HTMLDivElement, ResponsiveActionBarProps>(
  function ResponsiveActionBar({ children, className, ...rest }, ref) {
    return (
      <div
        {...rest}
        ref={ref}
        data-dn-responsive-action-bar="true"
        className={cn('dn-responsive-action-bar', className)}
      >
        {children}
      </div>
    )
  },
)

ResponsiveActionBar.displayName = 'ResponsiveActionBar'

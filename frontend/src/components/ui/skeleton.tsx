/**
 * v0.7.29 — Skeleton placeholder primitive (Shadcn convention).
 *
 * Used by the Dashboard Command Center for loading rows that feel
 * faster than a spinner. Pure utility — animates a subtle pulse on
 * a muted background that tracks the active theme.
 */
import * as React from 'react'

import { cn } from '@/lib/utils'

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-muted', className)}
      {...props}
    />
  )
}

export { Skeleton }

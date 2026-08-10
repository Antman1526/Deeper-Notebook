import * as React from 'react'

import { cn } from '@/lib/utils'

export interface FolioTabItem {
  id: string
  label: string
  badge?: React.ReactNode
}

export interface FolioTabProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  id: string
  label: React.ReactNode
  badge?: React.ReactNode
  selected?: boolean
  onActivate?: () => void
}

/** A single keyboard-operable tab used by FolioIndex and downstream surfaces. */
export const FolioTab = React.forwardRef<HTMLButtonElement, FolioTabProps>(
  function FolioTab(
    {
      id,
      label,
      badge,
      selected = false,
      onActivate,
      className,
      onClick,
      type = 'button',
      ...rest
    },
    ref,
  ) {
    return (
      <button
        {...rest}
        ref={ref}
        id={id}
        type={type}
        role="tab"
        aria-selected={selected}
        tabIndex={selected ? 0 : -1}
        data-dn-folio-tab="true"
        data-dn-folio-tab-id={id}
        className={cn('dn-folio-tab', className)}
        onClick={event => {
          onClick?.(event)
          if (!event.defaultPrevented) onActivate?.()
        }}
      >
        <span data-dn-folio-tab-label="true">{label}</span>
        {badge ? (
          <span data-dn-folio-tab-badge="true" aria-hidden="true">
            {badge}
          </span>
        ) : null}
      </button>
    )
  },
)

FolioTab.displayName = 'FolioTab'

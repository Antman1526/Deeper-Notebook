import * as React from 'react'

import { cn } from '@/lib/utils'

export interface FolioStateProps {
  kind: 'loading' | 'empty' | 'error' | 'offline' | 'permission'
  title: string
  description: string
  action?: React.ReactNode
}

const stateRole: Record<FolioStateProps['kind'], 'status' | 'alert'> = {
  loading: 'status',
  empty: 'status',
  error: 'alert',
  offline: 'status',
  permission: 'status',
}

/** Stable, explicit state surface for loading, empty, and recovery states. */
export const FolioState = React.forwardRef<HTMLElement, FolioStateProps>(
  function FolioState({ kind, title, description, action }, ref) {
    const generatedId = React.useId()
    const titleId = `${generatedId}-title`
    const descriptionId = `${generatedId}-description`
    const role = stateRole[kind]

    return (
      <section
        ref={ref}
        role={role}
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-live={role === 'alert' ? 'assertive' : 'polite'}
        data-dn-folio-state="true"
        data-dn-folio-state-kind={kind}
        className={cn('dn-folio-state', `dn-folio-state-${kind}`)}
      >
        <p data-dn-folio-state-kind-label="true" className="dn-folio-state-kind">
          {kind}
        </p>
        <h2 id={titleId} data-dn-folio-state-title="true">
          {title}
        </h2>
        <p id={descriptionId} data-dn-folio-state-description="true">
          {description}
        </p>
        {action ? (
          <div data-dn-folio-state-action="true" className="dn-folio-state-action">
            {action}
          </div>
        ) : null}
      </section>
    )
  },
)

FolioState.displayName = 'FolioState'

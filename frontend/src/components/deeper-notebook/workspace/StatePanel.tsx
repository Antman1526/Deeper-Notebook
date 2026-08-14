import * as React from 'react'

import { cn } from '@/lib/utils'

export type StatePanelKind =
  | 'loading'
  | 'empty'
  | 'processing'
  | 'degraded'
  | 'offline'
  | 'error'
  | 'unavailable'

export interface StatePanelProps
  extends Omit<React.HTMLAttributes<HTMLElement>, 'children' | 'title'> {
  kind: StatePanelKind
  title: string
  description: string
  preservation?: string
  action?: React.ReactNode
  details?: React.ReactNode
}

const stateRole: Record<StatePanelKind, 'status' | 'alert'> = {
  loading: 'status',
  empty: 'status',
  processing: 'status',
  degraded: 'status',
  offline: 'status',
  error: 'alert',
  unavailable: 'status',
}

/** Shared live-region surface for loading, empty, degraded, and recovery states. */
export const StatePanel = React.forwardRef<HTMLElement, StatePanelProps>(
  function StatePanel(
    {
      kind,
      title,
      description,
      preservation,
      action,
      details,
      className,
      'aria-labelledby': labelledByOverride,
      'aria-describedby': describedByOverride,
      ...rest
    },
    ref,
  ) {
    const generatedId = React.useId()
    const titleId = `${generatedId}-title`
    const descriptionId = `${generatedId}-description`
    const labelledBy = labelledByOverride ?? titleId
    const describedBy = describedByOverride ?? descriptionId
    const role = stateRole[kind]

    return (
      <section
        {...rest}
        ref={ref}
        role={role}
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        aria-live={role === 'alert' ? 'assertive' : 'polite'}
        aria-atomic="true"
        data-dn-state-panel="true"
        data-dn-state-panel-kind={kind}
        className={cn('dn-state-panel', `dn-state-panel-${kind}`, className)}
      >
        <p data-dn-state-panel-kind-label="true" className="dn-state-panel-kind">
          {kind}
        </p>
        <h2 id={titleId} data-dn-state-panel-title="true" className="dn-state-panel-title">
          {title}
        </h2>
        <p id={descriptionId} data-dn-state-panel-description="true" className="dn-state-panel-description">
          {description}
        </p>
        {preservation ? (
          <p data-dn-state-panel-preservation="true" className="dn-state-panel-preservation">
            {preservation}
          </p>
        ) : null}
        {action ? (
          <div data-dn-state-panel-action="true" className="dn-state-panel-action">
            {action}
          </div>
        ) : null}
        {details ? (
          <details data-dn-state-panel-details="true" className="dn-state-panel-details">
            <summary>Details</summary>
            <div data-dn-state-panel-details-content="true">{details}</div>
          </details>
        ) : null}
      </section>
    )
  },
)

StatePanel.displayName = 'StatePanel'

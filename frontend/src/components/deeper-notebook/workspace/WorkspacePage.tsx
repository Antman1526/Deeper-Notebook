import * as React from 'react'

import { cn } from '@/lib/utils'

export interface WorkspacePageProps
  extends Omit<React.HTMLAttributes<HTMLElement>, 'children' | 'title'> {
  title: React.ReactNode
  eyebrow?: React.ReactNode
  description?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
}

/** The page landmark and heading authority shared by workspace routes. */
export const WorkspacePage = React.forwardRef<HTMLElement, WorkspacePageProps>(
  function WorkspacePage(
    {
      title,
      eyebrow,
      description,
      actions,
      children,
      className,
      'aria-labelledby': labelledByOverride,
      ...rest
    },
    ref,
  ) {
    const generatedId = React.useId()
    const headingId = `${generatedId}-heading`
    const labelledBy = labelledByOverride ?? headingId

    return (
      <main
        {...rest}
        ref={ref}
        role="main"
        aria-labelledby={labelledBy}
        data-dn-workspace-page="true"
        className={cn('dn-workspace-page', className)}
      >
        <header data-dn-workspace-page-header="true" className="dn-workspace-page-header">
          <div data-dn-workspace-page-heading="true" className="dn-workspace-page-heading">
            {eyebrow ? (
              <p data-dn-workspace-page-eyebrow="true" className="dn-workspace-page-eyebrow">
                {eyebrow}
              </p>
            ) : null}
            <h1 id={headingId} data-dn-workspace-page-title="true" className="dn-workspace-page-title">
              {title}
            </h1>
            {description ? (
              <div data-dn-workspace-page-description="true" className="dn-workspace-page-description">
                {description}
              </div>
            ) : null}
          </div>
          {actions ? (
            <div data-dn-workspace-page-actions="true" className="dn-workspace-page-actions">
              {actions}
            </div>
          ) : null}
        </header>

        <div data-dn-workspace-page-content="true" className="dn-workspace-page-content">
          {children}
        </div>
      </main>
    )
  },
)

WorkspacePage.displayName = 'WorkspacePage'

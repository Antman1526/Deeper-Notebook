import * as React from 'react'

import { cn } from '@/lib/utils'

export interface WorkspaceHeroProps
  extends Omit<React.HTMLAttributes<HTMLElement>, 'children' | 'title'> {
  eyebrow?: React.ReactNode
  title: React.ReactNode
  description?: React.ReactNode
  image?: React.ReactNode
  actions?: React.ReactNode
}

/** A presentation-only introduction with an explicit caller-owned image slot. */
export const WorkspaceHero = React.forwardRef<HTMLElement, WorkspaceHeroProps>(
  function WorkspaceHero(
    {
      eyebrow,
      title,
      description,
      image,
      actions,
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
      <section
        {...rest}
        ref={ref}
        aria-labelledby={labelledBy}
        data-dn-workspace-hero="true"
        className={cn('dn-workspace-hero', className)}
      >
        {image ? (
          <div data-dn-workspace-hero-media="true" className="dn-workspace-hero-media">
            {image}
          </div>
        ) : null}
        <div data-dn-workspace-hero-copy="true" className="dn-workspace-hero-copy">
          {eyebrow ? (
            <p data-dn-workspace-hero-eyebrow="true" className="dn-workspace-hero-eyebrow">
              {eyebrow}
            </p>
          ) : null}
          <h2 id={headingId} data-dn-workspace-hero-title="true" className="dn-workspace-hero-title">
            {title}
          </h2>
          {description ? (
            <div data-dn-workspace-hero-description="true" className="dn-workspace-hero-description">
              {description}
            </div>
          ) : null}
          {actions ? (
            <div data-dn-workspace-hero-actions="true" className="dn-workspace-hero-actions">
              {actions}
            </div>
          ) : null}
        </div>
      </section>
    )
  },
)

WorkspaceHero.displayName = 'WorkspaceHero'

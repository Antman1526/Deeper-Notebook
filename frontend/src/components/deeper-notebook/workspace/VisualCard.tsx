'use client'

import * as React from 'react'

import { cn } from '@/lib/utils'

export type VisualCardInteraction =
  | { href: string; onActivate?: never }
  | { href?: never; onActivate(): void }
  | { href?: never; onActivate?: never }

export type VisualCardProps = VisualCardInteraction &
  Omit<React.HTMLAttributes<HTMLElement>, 'children' | 'title'> & {
    title: string
    description?: React.ReactNode
    media?: React.ReactNode
    metadata?: React.ReactNode
    children?: React.ReactNode
  }

/** Shared article geometry with at most one caller-owned activation action. */
export const VisualCard = React.forwardRef<HTMLElement, VisualCardProps>(
  function VisualCard(
    {
      title,
      description,
      media,
      metadata,
      children,
      href,
      onActivate,
      className,
      'aria-labelledby': labelledByOverride,
      ...rest
    },
    ref,
  ) {
    const generatedId = React.useId()
    const titleId = `${generatedId}-title`
    const labelledBy = labelledByOverride ?? titleId
    const actionLabel = `Open ${title}`

    return (
      <article
        {...rest}
        ref={ref}
        aria-labelledby={labelledBy}
        data-dn-visual-card="true"
        className={cn('dn-visual-card', className)}
      >
        {media ? (
          <div data-dn-visual-card-media="true" className="dn-visual-card-media">
            {media}
          </div>
        ) : null}
        <div data-dn-visual-card-body="true" className="dn-visual-card-body">
          <h2 id={titleId} data-dn-visual-card-title="true" className="dn-visual-card-title">
            {title}
          </h2>
          {description ? (
            <div data-dn-visual-card-description="true" className="dn-visual-card-description">
              {description}
            </div>
          ) : null}
          {children ? (
            <div data-dn-visual-card-content="true" className="dn-visual-card-content">
              {children}
            </div>
          ) : null}
          {metadata ? (
            <div data-dn-visual-card-metadata="true" className="dn-visual-card-metadata">
              {metadata}
            </div>
          ) : null}
          {href ? (
            <a
              href={href}
              aria-label={actionLabel}
              data-dn-visual-card-action="true"
              className="dn-visual-card-action"
            >
              {actionLabel}
            </a>
          ) : onActivate ? (
            <button
              type="button"
              onClick={onActivate}
              aria-label={actionLabel}
              data-dn-visual-card-action="true"
              className="dn-visual-card-action"
            >
              {actionLabel}
            </button>
          ) : null}
        </div>
      </article>
    )
  },
)

VisualCard.displayName = 'VisualCard'

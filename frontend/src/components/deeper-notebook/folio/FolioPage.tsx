import * as React from 'react'

import { cn } from '@/lib/utils'

export interface FolioPageProps
  extends Omit<React.HTMLAttributes<HTMLElement>, 'children' | 'title'> {
  eyebrow?: React.ReactNode
  title: React.ReactNode
  subtitle?: React.ReactNode
  actions?: React.ReactNode
  margin?: React.ReactNode
  children: React.ReactNode
  as?: 'main' | 'section' | 'article'
}

/**
 * The shared page landmark for a folio surface. A page owns one heading and
 * uses that heading as its accessible name, while the optional margin stays a
 * separate complementary region.
 */
export const FolioPage = React.forwardRef<HTMLElement, FolioPageProps>(
  function FolioPage(
    {
      as: Component = 'main',
      eyebrow,
      title,
      subtitle,
      actions,
      margin,
      children,
      className,
      ...rest
    },
    ref,
  ) {
    const generatedId = React.useId()
    const headingId = `${generatedId}-heading`
    const labelledBy = rest['aria-labelledby'] ?? headingId

    return (
      <Component
        {...rest}
        ref={ref}
        aria-labelledby={labelledBy}
        data-dn-folio-page="true"
        className={cn('dn-folio-page', className)}
      >
        <header data-dn-folio-page-header="true" className="dn-folio-page-header">
          <div data-dn-folio-page-heading="true">
            {eyebrow ? (
              <p data-dn-folio-page-eyebrow="true" className="dn-folio-page-eyebrow">
                {eyebrow}
              </p>
            ) : null}
            <h1 id={headingId} data-dn-folio-page-title="true" className="dn-folio-title">
              {title}
            </h1>
            {subtitle ? (
              <p data-dn-folio-page-subtitle="true" className="dn-folio-page-subtitle">
                {subtitle}
              </p>
            ) : null}
          </div>
          {actions ? (
            <div data-dn-folio-page-actions="true" className="dn-folio-page-actions">
              {actions}
            </div>
          ) : null}
        </header>

        <div data-dn-folio-page-content="true" className="dn-folio-page-content">
          {children}
        </div>

        {margin ? (
          <aside
            aria-label="Page margin"
            data-dn-folio-margin="true"
            className="dn-folio-margin"
          >
            {margin}
          </aside>
        ) : null}
      </Component>
    )
  },
)

FolioPage.displayName = 'FolioPage'

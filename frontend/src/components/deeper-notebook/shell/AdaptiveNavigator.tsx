'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'

import { getNavigation } from '@/components/layout/AppSidebar'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

function isActivePath(pathname: string | null, href: string) {
  return !!pathname && (pathname === href || pathname.startsWith(`${href}/`))
}

export function AdaptiveNavigator() {
  const pathname = usePathname()
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const navigation = getNavigation(t)

  return (
    <>
      <Button
        type="button"
        variant="outline"
        className="dn-navigator-toggle"
        aria-expanded={isOpen}
        aria-controls="dn-notebook-index"
        onClick={() => setIsOpen((open) => !open)}
      >
        Notebook index
      </Button>
      <nav
        id="dn-notebook-index"
        aria-label="Notebook index"
        className={cn('dn-adaptive-navigator', isOpen && 'is-open')}
        data-mobile-mode="sheet"
      >
        <div className="dn-navigator-heading">
          <p className="dn-command-kicker">Index</p>
          <h2>Notebook index</h2>
        </div>
        <div className="dn-navigator-list">
          {navigation.map((section) => (
            <div key={section.title} className="dn-navigator-section">
              <p className="dn-navigator-section-title">{section.title}</p>
              <ul>
                {section.items.map((item) => {
                  const active = isActivePath(pathname, item.href)
                  const Icon = item.icon
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        data-guided-tip-anchor={item.href}
                        aria-current={active ? 'page' : undefined}
                        className={cn('dn-navigator-link', active && 'is-active')}
                        onClick={() => setIsOpen(false)}
                      >
                        {active ? (
                          <span
                            id="onp-sidebar-active"
                            data-testid="onp-sidebar-active"
                            data-layout-id="onp-sidebar-active"
                            aria-hidden="true"
                          />
                        ) : null}
                        <Icon className="h-4 w-4" aria-hidden="true" />
                        <span>{item.name}</span>
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </div>
      </nav>
    </>
  )
}

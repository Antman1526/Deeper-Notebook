'use client'

import { ModelHealthIndicator } from '@/components/deeper-notebook/shell/ModelHealthIndicator'
import { getNavigation } from '@/components/layout/AppSidebar'
import { Menu, Search } from 'lucide-react'
import { usePathname } from 'next/navigation'

import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { requestCommandSurface } from '@/lib/commands/command-surface-store'
import { useIsMac } from '@/lib/hooks/use-is-mac'
import { useTranslation } from '@/lib/hooks/use-translation'
import { FocusModeControl } from './FocusModeControl'

interface CommandBarProps {
  /** v0.8.130 — Phase 3b: the V2 rail carries the brand, so its bar omits it. */
  showBrand?: boolean
  /** v0.8.130 — Phase 3b: below 1024px the V2 rail is a sheet opened from here. */
  onMenu?: () => void
  menuOpen?: boolean
  /** v0.8.130 — Phase 3b: V2 shows one keyboard hint, on Quick actions. */
  focusShortcut?: boolean
  /** v0.8.130 — model health while the rail is a sheet (below 1024px). */
  modelHealth?: boolean
}

export function CommandBar({ showBrand = true, onMenu, menuOpen = false, focusShortcut = true, modelHealth = false }: CommandBarProps = {}) {
  const pathname = usePathname()
  const { t } = useTranslation()
  const isMac = useIsMac()

  const routeSegment = pathname && pathname !== '/'
    ? pathname.split('/').filter(Boolean)[0]
    : 'notebook'
  // v0.8.130 — premium pass: sentence case ("Setup wizard"); the uppercase style
  // that used to hide the raw path segment is gone.
  const routeLabel = routeSegment.charAt(0).toUpperCase() + routeSegment.slice(1).replace(/-/g, ' ')
  // v0.8.130 — Phase 4c: the V2 crumb names the route the way the rail does, translated
  // (it printed the URL segment: "Setup wizard", and English in every language).
  const navItems = getNavigation(t).flatMap((section) => section.items)
  const navMatch = navItems
    .filter((item) => item.href !== '/' && pathname && (pathname === item.href || pathname.startsWith(`${item.href}/`)))
    .sort((a, b) => b.href.length - a.href.length)[0]
  const routeName = pathname === '/'
    ? t('navigation.home')
    : pathname?.startsWith('/setup-wizard')
      ? t('setupWizard.firstRun.title')
      : navMatch?.name ?? routeLabel

  return (
    <header className="dn-command-bar" aria-label="Command bar">
      <div className="dn-command-breadcrumb flex items-center gap-2.5">
        {onMenu ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="dn-command-menu"
            aria-label={t('common.menu')}
            aria-controls="dn-rail"
            aria-expanded={menuOpen}
            onClick={onMenu}
          >
            <Menu className="h-4 w-4" aria-hidden="true" />
          </Button>
        ) : null}
        {showBrand ? (
          <>
            {/* v0.8.130 — 12px type floor, and no hard-coded teal glow (the old brand hue in every theme). */}
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider bg-primary/10 text-primary border border-primary/20">
              <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
              <span className="dn-command-kicker m-0 leading-none">{routeLabel}</span>
            </span>
            <p className="dn-command-title font-semibold tracking-tight text-foreground">Deeper Notebook</p>
          </>
        ) : (
          <>
            {/* v0.8.130 — Phase 3b: the product name shows here while the rail (which carries
                it) is a sheet, below 1024px. */}
            <p className="dn-command-title dn-command-title--compact font-semibold tracking-tight text-foreground">Deeper Notebook</p>
            {/* A quiet breadcrumb; the home route reads "Home" (the chip's "Notebook"
                default named nothing). */}
            <span className="dn-command-kicker m-0 leading-none">{routeName}</span>
          </>
        )}
      </div>
      {/* v0.8.96 — the Focus control lives HERE, in flow, not floated over the
          bar. It used to be a shell-level sibling with position:absolute at the
          top-right, which put it directly on top of this trigger at every width.
          Flex layout removes the class of bug: no width reservation to keep in
          sync, nothing to drift when a shell's DOM changes. The legacy shell has
          no command bar and still renders it as a floated sibling. */}
      <div className="dn-command-actions">
        {modelHealth ? <ModelHealthIndicator /> : null}
        <Button
          type="button"
          variant="outline"
          className="dn-command-trigger group h-9 px-3 gap-2.5 border-border/80 bg-background/80 hover:bg-background/95 hover:border-primary/40 duration-150"
          aria-label="Open command palette"
          onClick={(event) => requestCommandSurface('global', '', event.currentTarget)}
        >
          <Search className="h-3.5 w-3.5 text-muted-foreground group-hover:text-primary transition-colors" aria-hidden="true" />
          <span className="text-sm font-medium text-muted-foreground group-hover:text-foreground transition-colors">{t('common.quickActions')}</span>
          {/* v0.8.130 — one platform-correct hint. The extra command icon doubled the glyph ("⌘ ⌘K"),
              and the chip showed a bare "K" before the platform was known. */}
          {/* v0.8.130 — the shared key chip (this one was hand-rolled at 10px). */}
          {isMac !== null ? (
            <Kbd className="dn-command-shortcut ml-auto" data-testid="command-shortcut">
              {isMac ? '⌘K' : 'Ctrl+K'}
            </Kbd>
          ) : null}
        </Button>
        <FocusModeControl showShortcut={focusShortcut} />
      </div>
    </header>
  )
}

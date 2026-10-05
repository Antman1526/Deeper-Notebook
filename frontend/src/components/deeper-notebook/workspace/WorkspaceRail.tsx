'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect } from 'react'
import { Book, FileText, LogOut, Mic, Plus } from 'lucide-react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { LocalModelHealthBadges } from '@/components/chat/LocalModelHealthBadges'
import { LanguageToggle } from '@/components/common/LanguageToggle'
import { GmailSidebarButton } from '@/components/deeper-notebook/GmailSidebarButton'
import { ThemeSwitcher } from '@/components/deeper-notebook/ThemeSwitcher'
import { useDesktopVersion } from '@/components/deeper-notebook/shell/use-desktop-version'
import { CREATE_TARGETS, getNavigation, type CreateTarget } from '@/components/layout/AppSidebar'
import { motion, useReducedMotion } from 'framer-motion'

import { useAuth } from '@/lib/hooks/use-auth'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

// v0.8.130 — Phase 3b: one rail for the V2 shell. It replaces the 68px instrument dock
// and the 272px "Notebook index" (340px of chrome at every width), lists the eight
// work destinations, and keeps the settings family (Models, Transformations, MCP
// Servers, Launch Preferences, Advanced) under Settings, shown when you are in it.
// The Luminous and legacy shells keep the dock and navigator.

const DESTINATIONS = ['/notebooks', '/sources', '/capture', '/knowledge', '/search', '/studio', '/podcasts', '/study']
const SETTINGS_HREF = '/settings'
const SETTINGS_FAMILY = ['/settings/api-keys', '/transformations', '/settings/mcp', '/settings/launcher-prefs', '/advanced']

function isActivePath(pathname: string | null, href: string) {
  return !!pathname && (pathname === href || pathname.startsWith(`${href}/`))
}

interface WorkspaceRailProps {
  /** Below 1024px the rail is a sheet; the shell owns whether it is open. */
  open: boolean
  onClose: () => void
}

export function WorkspaceRail({ open, onClose }: WorkspaceRailProps) {
  const pathname = usePathname()
  const { t } = useTranslation()
  const { logout } = useAuth()
  const { openSourceDialog, openNotebookDialog, openPodcastDialog } = useCreateDialogs()
  const version = useDesktopVersion()
  // Motion is decoration: the marker jumps, not glides, under either reduced-motion setting.
  const prefersReducedMotion = useReducedMotion()
  const stillMarker = prefersReducedMotion || (typeof document !== 'undefined' && document.documentElement.dataset.dnMotion === 'reduced')

  const items = getNavigation(t).flatMap((section) => section.items)
  const byHref = new Map<string, (typeof items)[number]>(items.map((item) => [item.href, item]))
  const destinations = DESTINATIONS.flatMap((href) => byHref.get(href) ?? [])
  const settings = byHref.get(SETTINGS_HREF)
  const settingsFamily = SETTINGS_FAMILY.flatMap((href) => byHref.get(href) ?? [])

  // The most specific matching link is the current page (/settings/mcp, not /settings).
  let activeHref: string | undefined
  for (const item of items) {
    if (isActivePath(pathname, item.href) && (!activeHref || item.href.length > activeHref.length)) {
      activeHref = item.href
    }
  }
  const inSettings = activeHref === SETTINGS_HREF || SETTINGS_FAMILY.includes(activeHref ?? '')

  // The sheet closes when a link changes the page, and on Escape.
  useEffect(() => {
    onClose()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on navigation
  }, [pathname])
  useEffect(() => {
    if (!open) return undefined
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const handleCreateSelection = (target: CreateTarget) => {
    if (target === 'source') openSourceDialog()
    if (target === 'notebook') openNotebookDialog()
    if (target === 'podcast') openPodcastDialog()
  }

  const renderLink = (item: (typeof items)[number], nested = false) => {
    const active = item.href === activeHref
    const Icon = item.icon
    return (
      <li key={item.href}>
        <Link
          href={item.href}
          data-guided-tip-anchor={item.href}
          aria-current={active ? 'page' : undefined}
          className={cn('dn-rail-link', nested && 'dn-rail-link--nested', active && 'is-active')}
        >
          {/* v0.8.130 — one marker for the whole rail: it glides from the page you were
              on to the page you are on (a shared layout), instead of blinking between rows. */}
          {active ? (
            <motion.span
              layoutId="dn-rail-marker"
              className="dn-rail-marker"
              aria-hidden="true"
              transition={stillMarker ? { duration: 0 } : { type: 'spring', stiffness: 520, damping: 38, mass: 0.7 }}
            />
          ) : null}
          {nested ? null : <Icon className="h-4 w-4" aria-hidden="true" />}
          <span className="truncate">{item.name}</span>
        </Link>
      </li>
    )
  }

  return (
    <>
      {open ? <div data-dn-rail-scrim="" className="dn-rail-scrim" aria-hidden="true" onClick={onClose} /> : null}
      <nav id="dn-rail" aria-label={t('navigation.primary')} className={cn('dn-rail', open && 'is-open')}>
        {/* v0.8.130 — Phase 4b: the logo is a link home. */}
        <Link href="/" className="dn-rail-brand" data-guided-tip-anchor="/">
          <span className="dn-rail-brand-mark" aria-hidden="true">DN</span>
          <span className="dn-rail-brand-name">Deeper Notebook</span>
        </Link>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" className="dn-rail-create w-full justify-start gap-2">
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('common.create')}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-48">
            {CREATE_TARGETS.map((target) => {
              const label = target === 'source' ? t('common.source') : target === 'notebook' ? t('common.notebook') : t('common.podcast')
              const Icon = target === 'source' ? FileText : target === 'notebook' ? Book : Mic
              return (
                <DropdownMenuItem key={target} onSelect={() => handleCreateSelection(target)} className="gap-2 cursor-pointer">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {label}
                </DropdownMenuItem>
              )
            })}
          </DropdownMenuContent>
        </DropdownMenu>

        <ul aria-label={t('navigation.destinations')} className="dn-rail-list">
          {destinations.map((item) => renderLink(item))}
        </ul>

        <div className="dn-rail-footer">
          {settings ? (
            <ul aria-label={t('navigation.settings')} className="dn-rail-list">
              {renderLink(settings)}
              {inSettings ? (
                <li>
                  <ul aria-label={t('navigation.settingsPages')} className="dn-rail-sublist">
                    {settingsFamily.map((item) => renderLink(item, true))}
                  </ul>
                </li>
              ) : null}
            </ul>
          ) : null}

          <div className="dn-rail-utilities">
            <ThemeSwitcher iconOnly />
            <LanguageToggle iconOnly />
            <GmailSidebarButton iconOnly />
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button type="button" variant="ghost" size="icon" aria-label={t('common.signOut')} title={t('common.signOut')}>
                  <LogOut className="h-4 w-4" aria-hidden="true" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t('auth.signOutTitle')}</AlertDialogTitle>
                  <AlertDialogDescription>{t('auth.signOutDescription')}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                  <AlertDialogAction onClick={logout}>{t('common.signOut')}</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>

          <div className="dn-rail-health" data-guided-tip-anchor="/settings/local-models">
            <LocalModelHealthBadges />
          </div>
          {version ? <p className="dn-rail-version">v{version}</p> : null}
        </div>
      </nav>
    </>
  )
}

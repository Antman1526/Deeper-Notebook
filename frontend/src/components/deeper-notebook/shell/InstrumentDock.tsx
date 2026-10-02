'use client'

import { Book, FileText, LogOut, Mic, Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { GmailSidebarButton } from '@/components/deeper-notebook/GmailSidebarButton'
import { ThemeSwitcher } from '@/components/deeper-notebook/ThemeSwitcher'
import { LocalModelHealthBadges } from '@/components/chat/LocalModelHealthBadges'
import { LanguageToggle } from '@/components/common/LanguageToggle'
import { useAuth } from '@/lib/hooks/use-auth'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import { CREATE_TARGETS, type CreateTarget } from '@/components/layout/AppSidebar'
import { useDesktopVersion } from './use-desktop-version'
import { useTranslation } from '@/lib/hooks/use-translation'

export function InstrumentDock() {
  const { t } = useTranslation()
  const { logout } = useAuth()
  const { openSourceDialog, openNotebookDialog, openPodcastDialog } = useCreateDialogs()

  const version = useDesktopVersion()

  const handleCreateSelection = (target: CreateTarget) => {
    if (target === 'source') openSourceDialog()
    if (target === 'notebook') openNotebookDialog()
    if (target === 'podcast') openPodcastDialog()
  }

  return (
    <nav
      aria-label="Primary tools"
      className="dn-instrument-dock"
      data-mobile-mode="bottom-tool-row"
    >
      <div className="dn-dock-brand" data-guided-tip-anchor="/">
        {/* v0.8.130 — no teal glow, no scale, named transitions (UI audit Phase 1) */}
        <span className="dn-dock-brand-mark ring-1 ring-primary/30" aria-hidden="true">DN</span>
        <span className="dn-dock-brand-name">Deeper Notebook</span>
      </div>

      <div className="dn-dock-create">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              aria-label={t('common.create')}
              className="w-full justify-center p-0 h-10 rounded-md group relative overflow-hidden bg-primary text-primary-foreground hover:bg-primary/95 duration-150"
            >
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-black/10 dark:bg-white/10 group-hover:bg-black/15 transition-colors duration-150">
                <Plus className="h-4 w-4" aria-hidden="true" />
              </span>
              {/* v0.8.130 — Only this span is visually hidden in the narrow dock; the icon
                  wrapper above must stay outside `.dn-dock-label`. */}
              <span className="dn-dock-label">{t('common.create')}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-48">
            {CREATE_TARGETS.map((target) => {
              const label = target === 'source'
                ? t('common.source')
                : target === 'notebook'
                  ? t('common.notebook')
                  : t('common.podcast')
              const Icon = target === 'source'
                ? FileText
                : target === 'notebook'
                  ? Book
                  : Mic
              return (
                <DropdownMenuItem
                  key={target}
                  onSelect={() => handleCreateSelection(target)}
                  className="gap-2 cursor-pointer"
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {label}
                </DropdownMenuItem>
              )
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="dn-dock-utilities" data-mobile-mode="utility-row">
        <div className="dn-dock-utility-row">
          <ThemeSwitcher iconOnly />
          <LanguageToggle iconOnly />
          <GmailSidebarButton iconOnly />
        </div>

        <Button
          type="button"
          variant="outline"
          className="w-full justify-start gap-3 rounded-md hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive duration-150"
          onClick={logout}
          aria-label={t('common.signOut')}
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          <span className="dn-dock-label">{t('common.signOut')}</span>
        </Button>

        <div className="dn-dock-health" data-guided-tip-anchor="/settings/local-models">
          <LocalModelHealthBadges />
        </div>

        {version ? <div className="dn-dock-version">v{version}</div> : null}
      </div>
    </nav>
  )
}

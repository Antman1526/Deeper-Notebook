'use client'

import { useState } from 'react'
import { LogOut, Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { GmailSidebarButton } from '@/components/deeper-notebook/GmailSidebarButton'
import { ThemeSwitcher } from '@/components/deeper-notebook/ThemeSwitcher'
import { LocalModelHealthBadges } from '@/components/chat/LocalModelHealthBadges'
import { LanguageToggle } from '@/components/common/LanguageToggle'
import { useAuth } from '@/lib/hooks/use-auth'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import { CREATE_TARGETS, type CreateTarget } from '@/components/layout/AppSidebar'
import { readDesktopVersion } from '@/lib/desktop-version'
import { useTranslation } from '@/lib/hooks/use-translation'

export function InstrumentDock() {
  const { t } = useTranslation()
  const { logout } = useAuth()
  const { openSourceDialog, openNotebookDialog, openPodcastDialog } = useCreateDialogs()
  const [createMenuOpen, setCreateMenuOpen] = useState(false)

  const handleCreateSelection = (target: CreateTarget) => {
    setCreateMenuOpen(false)
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
        <span className="dn-dock-brand-mark" aria-hidden="true">DN</span>
        <span className="dn-dock-brand-name">Deeper Notebook</span>
      </div>

      <div className="dn-dock-create">
        <Button
          type="button"
          aria-label={t('common.create')}
          aria-expanded={createMenuOpen}
          aria-haspopup="menu"
          onClick={() => setCreateMenuOpen((open) => !open)}
          className="w-full justify-start"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span>{t('common.create')}</span>
        </Button>
        {createMenuOpen ? (
          <div className="dn-create-menu" role="menu" aria-label={t('common.create')}>
            {CREATE_TARGETS.map((target) => {
              const label = target === 'source'
                ? t('common.source')
                : target === 'notebook'
                  ? t('common.notebook')
                  : t('common.podcast')
              return (
                <button key={target} type="button" role="menuitem" onClick={() => handleCreateSelection(target)}>
                  {label}
                </button>
              )
            })}
          </div>
        ) : null}
      </div>

      <div className="dn-dock-utilities">
        <div className="dn-dock-utility-row">
          <ThemeSwitcher />
          <LanguageToggle />
          <GmailSidebarButton />
        </div>

        <Button
          type="button"
          variant="outline"
          className="w-full justify-start gap-3"
          onClick={logout}
          aria-label={t('common.signOut')}
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          <span>{t('common.signOut')}</span>
        </Button>

        <div className="dn-dock-health" data-guided-tip-anchor="/settings/local-models">
          <LocalModelHealthBadges />
        </div>

        <div className="dn-dock-version" suppressHydrationWarning>
          v{typeof window !== 'undefined' ? (readDesktopVersion(window) || '—') : '—'}
        </div>
      </div>
    </nav>
  )
}

'use client'

import { useEffect, useState } from 'react'
import { Command, Search } from 'lucide-react'
import { usePathname } from 'next/navigation'

import { Button } from '@/components/ui/button'
import { requestCommandSurface } from '@/lib/commands/command-surface-store'
import { useTranslation } from '@/lib/hooks/use-translation'
import { FocusModeControl } from './FocusModeControl'

export function CommandBar() {
  const pathname = usePathname()
  const { t } = useTranslation()
  const [isMac, setIsMac] = useState<boolean | null>(null)

  useEffect(() => {
    setIsMac(navigator.platform.toLowerCase().includes('mac'))
  }, [])

  const routeLabel = pathname && pathname !== '/'
    ? pathname.split('/').filter(Boolean)[0]
    : 'notebook'

  return (
    <header className="dn-command-bar" aria-label="Command bar">
      <div className="dn-command-breadcrumb">
        <p className="dn-command-kicker">{routeLabel}</p>
        <p className="dn-command-title">Deeper Notebook</p>
      </div>
      {/* v0.8.96 — the Focus control lives HERE, in flow, not floated over the
          bar. It used to be a shell-level sibling with position:absolute at the
          top-right, which put it directly on top of this trigger at every width.
          Flex layout removes the class of bug: no width reservation to keep in
          sync, nothing to drift when a shell's DOM changes. The legacy shell has
          no command bar and still renders it as a floated sibling. */}
      <div className="dn-command-actions">
        <Button
          type="button"
          variant="outline"
          className="dn-command-trigger"
          aria-label="Open command palette"
          onClick={(event) => requestCommandSurface('global', '', event.currentTarget)}
        >
          <Search className="h-4 w-4" aria-hidden="true" />
          <span>{t('common.quickActions')}</span>
          <span className="dn-command-shortcut" data-testid="command-shortcut">
            <Command className="h-3 w-3" aria-hidden="true" />
            {isMac !== null ? (isMac ? '⌘K' : 'Ctrl+K') : 'K'}
          </span>
        </Button>
        <FocusModeControl />
      </div>
    </header>
  )
}

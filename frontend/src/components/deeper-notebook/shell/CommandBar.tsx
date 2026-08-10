'use client'

import { useEffect, useState } from 'react'
import { Command, Search } from 'lucide-react'
import { usePathname } from 'next/navigation'

import { Button } from '@/components/ui/button'
import { requestCommandSurface } from '@/lib/commands/command-surface-store'
import { useTranslation } from '@/lib/hooks/use-translation'

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
    <header className="dn-command-bar" aria-label="Command bar" data-guided-tip-anchor="/search">
      <div className="dn-command-breadcrumb">
        <p className="dn-command-kicker">{routeLabel}</p>
        <h1>Deeper Notebook</h1>
      </div>
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
    </header>
  )
}

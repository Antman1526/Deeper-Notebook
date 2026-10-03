'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'

export function ContextLens() {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <Button
        type="button"
        variant="outline"
        className="dn-context-lens-toggle"
        aria-expanded={isOpen}
        aria-controls="dn-context-lens"
        onClick={() => setIsOpen((open) => !open)}
      >
        {t('workspace.contextLens.toggle')}
      </Button>
      <aside
        id="dn-context-lens"
        aria-label={t('workspace.contextLens.ariaLabel')}
        className={`dn-context-lens${isOpen ? ' is-open' : ''}`}
        data-mobile-mode="overlay"
      >
        <div className="dn-context-lens-heading">
          <p className="dn-command-kicker">{t('workspace.contextLens.kicker')}</p>
          <h2>{t('workspace.contextLens.heading')}</h2>
        </div>
        <p className="dn-context-lens-copy">
          {t('workspace.contextLens.copy')}
        </p>
      </aside>
    </>
  )
}

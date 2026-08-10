'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'

export function ContextLens() {
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
        Context lens
      </Button>
      <aside
        id="dn-context-lens"
        aria-label="Context lens"
        className={`dn-context-lens${isOpen ? ' is-open' : ''}`}
        data-mobile-mode="overlay"
      >
        <div className="dn-context-lens-heading">
          <p className="dn-command-kicker">Context</p>
          <h2>Context lens</h2>
        </div>
        <p className="dn-context-lens-copy">
          Select a notebook section to keep its evidence, backlinks, and review
          context close at hand.
        </p>
      </aside>
    </>
  )
}

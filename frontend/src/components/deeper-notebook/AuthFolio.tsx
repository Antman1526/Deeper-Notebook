'use client'

import type { ReactNode } from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'

/** Presentation-only login cover; authentication remains owned by LoginForm. */
export function AuthFolio({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  return (
    <main
      aria-label={t('workspace.authFolio.ariaLabel')}
      className="grid min-h-screen place-items-center bg-[var(--dn-shell)] p-4 sm:p-8"
      data-dn-folio-page="true"
    >
      <section className="w-full max-w-md rounded-lg border border-[var(--dn-paper-edge)] bg-[var(--dn-folio-paper)] p-2 shadow-sm">
        <p className="px-4 pt-3 text-xs font-semibold text-[var(--dn-brass)]">
          Deeper Notebook
        </p>
        {children}
      </section>
    </main>
  )
}

'use client'

import type { ReactNode } from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'

/**
 * Presentation-only authentication frame. LoginForm remains the sole owner of
 * authentication state, requests, and submit behavior.
 */
export function WorkspaceAuthFrame({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  return (
    <main
      aria-labelledby="workspace-auth-title"
      data-testid="visual-system-v2-auth-frame"
      data-dn-visual-system="v2"
      className="dn-workspace-auth-frame"
    >
      <section className="dn-workspace-auth-panel">
        {/* v0.8.130 — Phase 3c: the one place the login names the product. */}
        <p className="dn-workspace-auth-brand">
          <span className="dn-rail-brand-mark" aria-hidden="true">DN</span>
          Deeper Notebook
        </p>
        <h1 id="workspace-auth-title" className="dn-workspace-auth-title">
          {t('auth.welcomeBack')}
        </h1>
        <p className="dn-workspace-auth-description">
          {t('auth.welcomeDescription')}
        </p>
        <div className="dn-workspace-auth-content">{children}</div>
      </section>
    </main>
  )
}

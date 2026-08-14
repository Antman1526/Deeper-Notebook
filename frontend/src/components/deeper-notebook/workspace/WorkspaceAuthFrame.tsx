import type { ReactNode } from 'react'

/**
 * Presentation-only authentication frame. LoginForm remains the sole owner of
 * authentication state, requests, and submit behavior.
 */
export function WorkspaceAuthFrame({ children }: { children: ReactNode }) {
  return (
    <main
      aria-labelledby="workspace-auth-title"
      data-testid="visual-system-v2-auth-frame"
      data-dn-visual-system="v2"
      className="dn-workspace-auth-frame"
    >
      <section className="dn-workspace-auth-panel">
        <p className="dn-workspace-auth-eyebrow">Deeper Notebook</p>
        <h1 id="workspace-auth-title" className="dn-workspace-auth-title">
          Welcome back
        </h1>
        <p className="dn-workspace-auth-description">
          Continue working with your local sources, notebooks, and grounded questions.
        </p>
        <div className="dn-workspace-auth-content">{children}</div>
      </section>
    </main>
  )
}

import type { ReactNode } from 'react'

/** Presentation-only login cover; authentication remains owned by LoginForm. */
export function AuthFolio({ children }: { children: ReactNode }) {
  return (
    <main
      aria-label="Deeper Notebook sign in"
      className="grid min-h-screen place-items-center bg-[var(--dn-shell)] p-4 sm:p-8"
      data-dn-folio-page="true"
    >
      <section className="w-full max-w-md rounded-lg border border-[var(--dn-paper-edge)] bg-[var(--dn-folio-paper)] p-2 shadow-sm">
        <p className="px-4 pt-3 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--dn-brass)]">
          Deeper Notebook
        </p>
        {children}
      </section>
    </main>
  )
}

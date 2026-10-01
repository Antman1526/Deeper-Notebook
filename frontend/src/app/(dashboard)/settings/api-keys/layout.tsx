import type { Metadata } from 'next'

// v0.8.130 — Phase 3a: names this route in the document title. Absolute because the
// parent segment's own title stops the root "%s · Deeper Notebook" template reaching here.
export const metadata: Metadata = { title: { absolute: 'Models · Deeper Notebook' } }

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}

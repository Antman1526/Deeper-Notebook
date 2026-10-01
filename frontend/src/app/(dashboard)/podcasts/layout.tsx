import type { Metadata } from 'next'

// v0.8.130 — Phase 3a: names this route in the document title ("Podcasts · Deeper Notebook").
export const metadata: Metadata = { title: 'Podcasts' }

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}

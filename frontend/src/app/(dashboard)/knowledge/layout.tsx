import type { Metadata } from 'next'

// v0.8.130 — Phase 3a: names this route in the document title ("Knowledge · Deeper Notebook").
export const metadata: Metadata = { title: 'Knowledge' }

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}

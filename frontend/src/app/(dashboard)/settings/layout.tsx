import type { Metadata } from 'next'

// v0.8.130 — Phase 3a: names this route in the document title ("Settings · Deeper Notebook").
export const metadata: Metadata = { title: 'Settings' }

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}

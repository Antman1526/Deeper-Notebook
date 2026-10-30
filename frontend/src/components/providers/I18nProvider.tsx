'use client'

import React, { useEffect, useState } from 'react'
import i18n from '@/lib/i18n'
import { LanguageLoadingOverlay } from '@/components/common/LanguageLoadingOverlay'
import { DocumentTitle } from '@/components/providers/DocumentTitle'

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false)
  const [languageReady, setLanguageReady] = useState(false)

  useEffect(() => {
    setMounted(true)
    // v0.8.130 — the document language follows the UI language, so screen readers use the
    // right voice and CSS hyphenation can break long words. Set after hydration: the
    // root layout renders lang="en" on the server.
    const syncDocumentLanguage = (language: string) => {
      if (language) document.documentElement.lang = language
    }
    syncDocumentLanguage(i18n.language)
    i18n.on('languageChanged', syncDocumentLanguage)

    // v0.8.130 — languages other than English load on demand; stay hidden until the
    // active one has arrived, so the page never flashes English first. If loading fails
    // the English fallback shows after a short wait rather than a blank window.
    const markReady = () => {
      if (i18n.isInitialized && i18n.hasLoadedNamespace('translation')) setLanguageReady(true)
    }
    markReady()
    i18n.on('initialized', markReady)
    i18n.on('loaded', markReady)
    const fallback = window.setTimeout(() => setLanguageReady(true), 3000)
    return () => {
      i18n.off('languageChanged', syncDocumentLanguage)
      i18n.off('initialized', markReady)
      i18n.off('loaded', markReady)
      window.clearTimeout(fallback)
    }
  }, [])

  // Avoid hydration mismatch by waiting for mount (and for the active language).
  if (!mounted || !languageReady) {
    return <div style={{ visibility: 'hidden' }}>{children}</div>
  }

  return (
    <>
      <LanguageLoadingOverlay />
      <DocumentTitle />
      {children}
    </>
  )
}

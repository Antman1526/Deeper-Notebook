'use client'

import React, { useEffect, useState } from 'react'
import i18n from '@/lib/i18n'
import { LanguageLoadingOverlay } from '@/components/common/LanguageLoadingOverlay'

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false)

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
    return () => i18n.off('languageChanged', syncDocumentLanguage)
  }, [])

  // Avoid hydration mismatch by waiting for mount
  if (!mounted) {
    return <div style={{ visibility: 'hidden' }}>{children}</div>
  }

  return (
    <>
      <LanguageLoadingOverlay />
      {children}
    </>
  )
}

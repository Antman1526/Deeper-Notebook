'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { sourcesApi } from '@/lib/api/sources'
import { useTranslation } from '@/lib/hooks/use-translation'

type PassageMatch = { start: number; end: number; score: number; snippet: string } | null

type EvidencePeekProps = {
  sourceId: string
  title: string
  evidenceQuery: string | null | undefined
  onClose: () => void
}

export function EvidencePeek({ sourceId, title, evidenceQuery, onClose }: EvidencePeekProps) {
  const { t } = useTranslation()
  const [match, setMatch] = useState<PassageMatch>(null)
  const [loading, setLoading] = useState(Boolean(evidenceQuery?.trim()))
  const closeRef = useRef<HTMLButtonElement>(null)
  const invokerRef = useRef<HTMLElement | null>(null)
  const scrollPositionRef = useRef({ left: 0, top: 0 })
  const closedRef = useRef(false)

  const close = useCallback(() => {
    if (closedRef.current) return
    closedRef.current = true
    onClose()
    window.scrollTo({ ...scrollPositionRef.current, behavior: 'auto' })
    invokerRef.current?.focus()
  }, [onClose])

  useEffect(() => {
    invokerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    scrollPositionRef.current = { left: window.scrollX, top: window.scrollY }
    closeRef.current?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [close])

  useEffect(() => {
    if (!evidenceQuery || !evidenceQuery.trim()) {
      setLoading(false)
      setMatch(null)
      return
    }

    let cancelled = false
    setLoading(true)
    sourcesApi.locatePassage(sourceId, evidenceQuery)
      .then(result => {
        if (!cancelled) setMatch(result)
      })
      .catch(() => {
        if (!cancelled) setMatch(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [sourceId, evidenceQuery])

  return (
    <section className="dn-evidence-peek" role="dialog" aria-modal="true" aria-labelledby="evidence-peek-title">
      <div className="dn-evidence-peek__header">
        <h2 id="evidence-peek-title">{t('workspace.evidencePeek.heading', { title })}</h2>
        <button ref={closeRef} type="button" onClick={close} aria-label={t('workspace.evidencePeek.closeLabel')}>
          {t('common.close')}
        </button>
      </div>
      {loading ? <p role="status">{t('workspace.evidencePeek.finding')}</p> : null}
      {!loading && match ? (
        <div className="dn-evidence-peek__match">
          <p>{match.snippet}</p>
          <p>{t('workspace.evidencePeek.matchConfidence', { percent: Math.round(match.score * 100) })}</p>
        </div>
      ) : null}
      {!loading && !match ? <p role="status">{t('workspace.evidencePeek.unavailable')}</p> : null}
    </section>
  )
}

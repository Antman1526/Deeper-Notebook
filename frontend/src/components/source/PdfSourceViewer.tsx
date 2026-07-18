'use client'

// v0.8.82 — inline PDF rendering (improvement roadmap, Batch 2). Renders an
// uploaded PDF source inline via react-pdf, fetched as a blob from the existing
// GET /sources/{id}/download endpoint. The pdfjs worker is bundled LOCALLY
// (public/pdf.worker.min.mjs, copied from pdfjs-dist) — NO CDN, in keeping with
// the local-first/offline ethos. This is loaded with next/dynamic ssr:false by
// the caller, because react-pdf needs the DOM + worker (no SSR).
//
// ⚠️ NEEDS AN IN-APP TEST: the offline worker + WKWebView blob rendering can't
// be verified headlessly. On any load error this component reports up via
// onUnavailable so the caller falls back to the extracted-text view.
import { useEffect, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import { Loader2 } from 'lucide-react'

import { sourcesApi } from '@/lib/api/sources'

// Local, offline worker — matched to the pdfjs-dist version react-pdf bundles.
pdfjs.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs'

interface PdfSourceViewerProps {
  sourceId: string
  /** Called when the PDF can't be fetched/rendered, so the caller can fall back. */
  onUnavailable?: () => void
}

export default function PdfSourceViewer({ sourceId, onUnavailable }: PdfSourceViewerProps) {
  const [url, setUrl] = useState<string | null>(null)
  const [numPages, setNumPages] = useState(0)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let objectUrl: string | null = null
    let cancelled = false

    sourcesApi
      .downloadFile(sourceId)
      .then((resp) => {
        if (cancelled) return
        const data = resp.data
        const blob =
          data instanceof Blob ? data : new Blob([data], { type: 'application/pdf' })
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => {
        if (cancelled) return
        setFailed(true)
        onUnavailable?.()
      })

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [sourceId, onUnavailable])

  if (failed) return null

  if (!url) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="max-h-[65vh] overflow-y-auto rounded-md border bg-muted/20 p-2">
      <Document
        file={url}
        onLoadSuccess={({ numPages: n }) => setNumPages(n)}
        onLoadError={() => {
          setFailed(true)
          onUnavailable?.()
        }}
        loading={
          <div className="py-10 text-center text-xs text-muted-foreground">Loading PDF…</div>
        }
        error={
          <div className="py-10 text-center text-xs text-muted-foreground">
            Couldn’t render the PDF — showing the extracted text instead.
          </div>
        }
      >
        {Array.from({ length: numPages }, (_, i) => (
          <Page
            key={i}
            pageNumber={i + 1}
            width={740}
            renderTextLayer
            renderAnnotationLayer={false}
            className="mx-auto my-2 shadow-sm"
          />
        ))}
      </Document>
    </div>
  )
}

'use client'

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
} from 'react'

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { VaultLink, VaultPage } from '@/lib/api/vault'
import { useVaultPagePreview } from '@/lib/hooks/use-vault'

const previewIntentDelayMs = 250
const excerptLimit = 240

interface VaultPagePreviewProps {
  vaultId: string
  link: VaultLink
  trigger: ReactElement
  onNavigate?: (noteId: string) => void
}

function isCanonicalRelativePath(value: string | null | undefined): value is string {
  if (!value || value.trim() !== value) return false
  return !value.startsWith('/')
    && !/^[A-Za-z]:/.test(value)
    && !value.includes('\\')
    && !value.split('/').some((segment) => !segment || segment === '.' || segment === '..')
}

function truncateCodePoints(value: string): string {
  let result = ''
  let count = 0
  for (const codePoint of value) {
    if (count === excerptLimit) break
    result += codePoint
    count += 1
  }
  return result
}

function excerpts(page: VaultPage): string[] {
  const result: string[] = []
  for (const block of page.blocks) {
    const markdown = block.markdown?.trim()
    if (!markdown) continue
    result.push(truncateCodePoints(markdown))
    if (result.length === 3) break
  }
  return result
}

export function VaultPagePreview({
  vaultId,
  link,
  trigger,
  onNavigate,
}: VaultPagePreviewProps) {
  const targetNoteId = link.resolved ? link.target_note_id : null
  const canOpen = Boolean(
    targetNoteId && isCanonicalRelativePath(link.target_relative_path),
  )
  const [intent, setIntent] = useState(false)
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hovered = useRef(false)
  const focused = useRef(false)
  const linkIdentity = JSON.stringify([
    vaultId,
    link.id,
    targetNoteId,
    link.target_relative_path,
  ])
  const previousLinkIdentity = useRef(linkIdentity)
  const [mismatchedLinkIdentity, setMismatchedLinkIdentity] = useState<
    string | null
  >(null)
  const preview = useVaultPagePreview(vaultId, targetNoteId || undefined, intent && canOpen)
  const page = preview.data
  const path = page?.file.relative_path
  const pageMatchesTarget = Boolean(
    page
    && targetNoteId
    && page.file.vault_id === vaultId
    && page.file.note_id === targetNoteId,
  )
  const observedPathMismatch = Boolean(
    pageMatchesTarget
    && link.target_relative_path
    && path !== link.target_relative_path,
  )
  const pathMismatchLatched = mismatchedLinkIdentity === linkIdentity
  const navigationBlocked = observedPathMismatch || pathMismatchLatched
  const previewExcerpts = useMemo(
    () => pageMatchesTarget && page ? excerpts(page) : [],
    [page, pageMatchesTarget],
  )
  const canDisplay = Boolean(
    !preview.isError
    && pageMatchesTarget
    && page
    && !navigationBlocked
    && isCanonicalRelativePath(path)
    && path === link.target_relative_path
  )

  const cancelPendingIntent = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current)
      timer.current = null
    }
    setPending(false)
  }, [])

  const closePreview = useCallback(() => {
    cancelPendingIntent()
    setIntent(false)
    setOpen(false)
  }, [cancelPendingIntent])

  const beginIntent = useCallback(() => {
    if (!canOpen || navigationBlocked || timer.current) return
    setPending(true)
    timer.current = setTimeout(() => {
      timer.current = null
      setPending(false)
      setIntent(true)
      setOpen(true)
    }, previewIntentDelayMs)
  }, [canOpen, navigationBlocked])

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current)
  }, [])

  useEffect(() => {
    if (!pending && !open) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closePreview()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [closePreview, open, pending])

  useEffect(() => {
    if (previousLinkIdentity.current === linkIdentity) return
    previousLinkIdentity.current = linkIdentity
    setMismatchedLinkIdentity(null)
    closePreview()
  }, [closePreview, linkIdentity])

  useEffect(() => {
    if (observedPathMismatch) {
      setMismatchedLinkIdentity(linkIdentity)
      closePreview()
      return
    }
    if (preview.isError) closePreview()
  }, [
    closePreview,
    linkIdentity,
    observedPathMismatch,
    preview.isError,
  ])

  return (
    <Popover
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) closePreview()
      }}
    >
      <span
        onMouseEnter={() => {
          hovered.current = true
          beginIntent()
        }}
        onMouseLeave={() => {
          hovered.current = false
          if (!focused.current) cancelPendingIntent()
        }}
        onFocus={() => {
          focused.current = true
          beginIntent()
        }}
        onBlur={() => {
          focused.current = false
          if (!hovered.current) cancelPendingIntent()
        }}
        onClick={() => {
          if (canOpen && targetNoteId && !navigationBlocked) {
            onNavigate?.(targetNoteId)
          }
        }}
      >
        <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      </span>
      {canDisplay && page && path && (
        <PopoverContent
          aria-label={`${page.note.title || link.target_text} preview`}
          className="w-80 space-y-3"
        >
          <div>
            <p className="font-medium">
              {page.note.title || link.target_text}
            </p>
            <p className="text-sm text-muted-foreground">{path}</p>
            <p className="text-xs text-muted-foreground">
              {page.note.source_format || page.file.format}
            </p>
          </div>
          {previewExcerpts.length > 0 && (
            <div className="space-y-2 text-sm text-muted-foreground">
              {previewExcerpts.map((excerpt, index) => (
                <p key={`${index}-${excerpt}`}>{excerpt}</p>
              ))}
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            {page.outgoing_links.length} outgoing · {page.backlinks.length} backlinks
          </p>
        </PopoverContent>
      )}
    </Popover>
  )
}

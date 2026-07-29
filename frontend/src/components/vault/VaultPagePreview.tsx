'use client'

import {
  useCallback,
  useEffect,
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

function excerpts(page: VaultPage): string[] {
  return page.blocks
    .map((block) => block.markdown?.trim())
    .filter((block): block is string => Boolean(block))
    .slice(0, 3)
    .map((block) => block.slice(0, excerptLimit))
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
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const preview = useVaultPagePreview(vaultId, targetNoteId || undefined, intent && canOpen)

  const clearIntentTimer = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  const closePreview = useCallback(() => {
    clearIntentTimer()
    setIntent(false)
    setOpen(false)
  }, [clearIntentTimer])

  const beginIntent = useCallback(() => {
    if (!canOpen || timer.current) return
    timer.current = setTimeout(() => {
      timer.current = null
      setIntent(true)
      setOpen(true)
    }, previewIntentDelayMs)
  }, [canOpen])

  useEffect(() => () => clearIntentTimer(), [clearIntentTimer])

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closePreview()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [closePreview])

  const page = preview.data
  const path = page?.file.relative_path
  const canDisplay = Boolean(
    !preview.isError
    && page
    && isCanonicalRelativePath(path),
  )

  return (
    <Popover
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) closePreview()
      }}
    >
      <span
        onMouseEnter={() => {
          beginIntent()
        }}
        onFocus={() => {
          beginIntent()
        }}
        onClick={() => {
          if (canOpen && targetNoteId) onNavigate?.(targetNoteId)
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
          {excerpts(page).length > 0 && (
            <div className="space-y-2 text-sm text-muted-foreground">
              {excerpts(page).map((excerpt, index) => (
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

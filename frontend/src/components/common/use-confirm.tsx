'use client'

import { useCallback, useRef, useState, type ReactNode } from 'react'

import { ConfirmDialog } from './ConfirmDialog'

// v0.8.130 — Phase 4c of the 2026-09-30 UI audit: an awaitable stand-in for the
// browser's confirm(), which is unstyled, untranslatable and blocks the page.
//
//   const { confirm, dialog } = useConfirm()
//   if (!(await confirm({ title, description, destructive: true }))) return
//   ...and render {dialog}.

export interface ConfirmOptions {
  title: string
  description: string
  confirmText?: string
  destructive?: boolean
}

export function useConfirm(): { confirm: (options: ConfirmOptions) => Promise<boolean>; dialog: ReactNode } {
  const [open, setOpen] = useState(false)
  // Kept after closing so the dialog keeps its text while it animates out.
  const [options, setOptions] = useState<ConfirmOptions | null>(null)
  const resolver = useRef<((value: boolean) => void) | null>(null)

  const settle = useCallback((value: boolean) => {
    resolver.current?.(value)
    resolver.current = null
    setOpen(false)
  }, [])

  const confirm = useCallback((next: ConfirmOptions) => new Promise<boolean>((resolve) => {
    resolver.current?.(false)
    resolver.current = resolve
    setOptions(next)
    setOpen(true)
  }), [])

  const dialog = (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) settle(false)
      }}
      title={options?.title ?? ''}
      description={options?.description ?? ''}
      confirmText={options?.confirmText}
      confirmVariant={options?.destructive ? 'destructive' : 'default'}
      onConfirm={() => settle(true)}
    />
  )

  return { confirm, dialog }
}

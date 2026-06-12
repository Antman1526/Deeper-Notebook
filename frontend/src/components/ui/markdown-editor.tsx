'use client'

import dynamic from 'next/dynamic'
import { forwardRef } from 'react'
// v0.8.67q — was `next-themes`, whose provider is NOT initialized in this app
// (we use the Zustand theme store). next-themes' useTheme() therefore returned
// undefined, so the editor silently fell back to light mode regardless of the
// app theme — a white editor inside a dark dialog. Use the real theme store.
import { useTheme } from '@/lib/stores/theme-store'

const MDEditor = dynamic(
  () => import('@uiw/react-md-editor').then((mod) => mod.default),
  { ssr: false }
)

export interface MarkdownEditorProps {
  value?: string
  onChange?: (value?: string) => void
  placeholder?: string
  height?: number
  preview?: 'live' | 'edit' | 'preview'
  hideToolbar?: boolean
  textareaId?: string
  name?: string
  className?: string
}

export const MarkdownEditor = forwardRef<HTMLDivElement, MarkdownEditorProps>(
  ({ value = '', onChange, placeholder, height = 300, preview = 'live', hideToolbar = false, className, textareaId, name }, ref) => {
    // v0.7.201 — follow the app's next-themes setting instead of
    // hardcoding `data-color-mode="light"`. Before, the editor
    // rendered with a white background against a dark dialog when
    // dark mode was active; obvious visual mismatch for note
    // editing. `resolvedTheme` resolves "system" to the actual
    // light/dark choice; SSR fallback is "light" because MDEditor
    // is ssr:false anyway.
    const { effectiveTheme } = useTheme()
    const colorMode: 'light' | 'dark' =
      effectiveTheme === 'dark' ? 'dark' : 'light'
    return (
      <div className={className} ref={ref} data-color-mode={colorMode}>
        <MDEditor
          value={value}
          onChange={onChange}
          preview={preview}
          height={height}
          hideToolbar={hideToolbar}
          textareaProps={{
            placeholder: placeholder || 'Enter markdown...',
            id: textareaId,
            name: name,
          }}
          data-color-mode={colorMode}
        />
      </div>
    )
  }
)

MarkdownEditor.displayName = 'MarkdownEditor'
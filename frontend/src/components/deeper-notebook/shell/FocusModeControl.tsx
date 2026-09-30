'use client'

import { Focus, Minimize2 } from 'lucide-react'
import { useEffect } from 'react'

import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { useIsMac } from '@/lib/hooks/use-is-mac'
import { useDisplayPreferencesStore } from '@/lib/stores/display-preferences-store'

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return true
  return Boolean(target.closest('[contenteditable="true"]'))
}

export function FocusModeControl() {
  const focusMode = useDisplayPreferencesStore((state) => state.focusMode)
  const setFocusMode = useDisplayPreferencesStore((state) => state.setFocusMode)
  const toggleFocusMode = useDisplayPreferencesStore((state) => state.toggleFocusMode)

  useEffect(() => {
    const root = document.documentElement
    root.dataset.dnFocusMode = focusMode ? 'true' : 'false'

    const handleKeyDown = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) return

      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === 'f') {
        event.preventDefault()
        toggleFocusMode()
        return
      }

      if (event.key === 'Escape' && focusMode) {
        event.preventDefault()
        setFocusMode(false)
      }
    }

    document.addEventListener('keydown', handleKeyDown, true)
    return () => document.removeEventListener('keydown', handleKeyDown, true)
  }, [focusMode, setFocusMode, toggleFocusMode])

  const label = focusMode ? 'Exit Focus mode' : 'Enter Focus mode'
  const isMac = useIsMac()
  // v0.8.130 — One shortcut for the platform in use; none until the platform is known.
  const shortcut = isMac === null ? null : isMac ? '⌘⇧F' : 'Ctrl+Shift+F'

  return (
    <Button
      type="button"
      variant={focusMode ? 'secondary' : 'outline'}
      aria-label={label}
      aria-pressed={focusMode}
      data-testid="focus-mode-control"
      data-focus-active={focusMode ? 'true' : 'false'}
      data-focus-shortcut={shortcut ?? undefined}
      title={shortcut ? `${label} (${shortcut})` : label}
      className="dn-focus-mode-control motion-reduce:transition-none"
      onClick={toggleFocusMode}
    >
      {focusMode ? (
        <Minimize2 aria-hidden="true" className="h-4 w-4" />
      ) : (
        <Focus aria-hidden="true" className="h-4 w-4" />
      )}
      <span className="dn-focus-mode-label">{label}</span>
      {!focusMode && shortcut ? (
        // v0.8.130 — the shared key chip.
        <Kbd className="dn-focus-mode-shortcut" aria-hidden="true">{shortcut}</Kbd>
      ) : null}
    </Button>
  )
}

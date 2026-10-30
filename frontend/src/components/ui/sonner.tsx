"use client"

import { useSyncExternalStore } from "react"
import { Toaster as Sonner, ToasterProps } from "sonner"

// v0.8.130 — Phase 4c of the 2026-09-30 UI audit: toasts follow the active theme (the
// catalog themes toggle .dark on <html>; the legacy light/dark store did not know a
// dark catalog theme was on), and every kind is styled from the theme tokens. Only
// normal and success were; 74 error toasts used Sonner's defaults.

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
  return () => observer.disconnect()
}

function documentTheme(): "light" | "dark" {
  return document.documentElement.classList.contains("dark") ? "dark" : "light"
}

const Toaster = ({ ...props }: ToasterProps) => {
  const theme = useSyncExternalStore(subscribe, documentTheme, () => "light" as const)

  return (
    <Sonner
      theme={theme}
      // The per-kind variables below only apply with rich colours on.
      richColors
      className="toaster group"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--success-bg": "var(--popover)",
          "--success-text": "var(--popover-foreground)",
          "--success-border": "var(--border)",
          "--error-bg": "var(--destructive-soft)",
          "--error-text": "var(--destructive-ink)",
          "--error-border": "var(--destructive)",
          "--warning-bg": "var(--warning-soft)",
          "--warning-text": "var(--warning-ink)",
          "--warning-border": "var(--warning)",
          "--info-bg": "var(--info-soft)",
          "--info-text": "var(--info-ink)",
          "--info-border": "var(--info)",
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }

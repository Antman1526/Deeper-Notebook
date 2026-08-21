'use client'

import type { CSSProperties } from 'react'
import { Check, Eye } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { ThemeDefinition } from '@/lib/themes/catalog'

interface ThemePreviewCardProps {
  theme: ThemeDefinition
  selected: boolean
  previewing: boolean
  onPreview: () => void
  onApply: () => void
}

export function ThemePreviewCard({
  theme,
  selected,
  previewing,
  onPreview,
  onApply,
}: ThemePreviewCardProps) {
  const previewProperties = {
    '--preview-canvas': theme.preview.canvas,
    '--preview-panel': theme.preview.panel,
    '--preview-text': theme.preview.text,
    '--preview-primary': theme.preview.primary,
    '--preview-accent': theme.preview.accent,
    '--preview-border': theme.preview.border,
  } as CSSProperties

  return (
    <article
      className={cn(
        'group rounded-xl border bg-card p-3 transition-[border-color,box-shadow]',
        selected && 'border-primary/70 ring-1 ring-primary/20',
        previewing && 'border-accent-foreground/40 ring-1 ring-accent-foreground/15',
      )}
      aria-label={`${theme.label} theme`}
    >
      <div className="overflow-hidden rounded-lg border shadow-sm" style={previewProperties}>
        <div className="grid h-24 grid-cols-[1.35rem_1fr_.8fr] bg-[var(--preview-canvas)] text-[var(--preview-text)]">
          <div className="border-r border-[var(--preview-border)] bg-[var(--preview-panel)]" />
          <div className="space-y-2 p-2">
            <div className="h-2 w-10 rounded bg-[var(--preview-primary)]" />
            <div className="h-1.5 w-full rounded bg-[var(--preview-border)]" />
            <div className="h-1.5 w-3/4 rounded bg-[var(--preview-border)]" />
          </div>
          <div className="m-2 rounded border border-[var(--preview-border)] bg-[var(--preview-panel)]">
            <div className="m-2 h-2 rounded bg-[var(--preview-accent)]" />
          </div>
        </div>
      </div>

      <div className="mt-3 flex min-h-12 items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-sm font-semibold leading-tight">{theme.label}</h4>
            {selected && (
              <span
                className="rounded-full bg-primary/10 px-2 py-0.5 text-[0.625rem] font-semibold uppercase tracking-wide text-primary"
                aria-label="Current theme"
              >
                Current
              </span>
            )}
            {previewing && (
              <span
                className="rounded-full bg-accent px-2 py-0.5 text-[0.625rem] font-semibold uppercase tracking-wide text-accent-foreground"
                aria-label="Previewing theme"
              >
                Previewing
              </span>
            )}
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{theme.description}</p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-pressed={previewing}
          aria-label={`Preview ${theme.label}`}
          onClick={onPreview}
        >
          <Eye aria-hidden="true" />
          Preview
        </Button>
        <Button
          type="button"
          size="sm"
          aria-label={`Apply ${theme.label}`}
          onClick={onApply}
        >
          <Check aria-hidden="true" />
          Apply
        </Button>
      </div>
    </article>
  )
}

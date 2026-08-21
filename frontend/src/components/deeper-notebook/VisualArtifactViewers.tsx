'use client'

import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, StickyNote } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface VisualSlide {
  title: string
  bullets: string[]
  speaker_notes: string
  visual_direction: string
  citations: string[]
}

export interface SlideDeckVisualDocument {
  schema_version: 1
  artifact_type: 'slide_deck'
  title: string
  audience: string
  slides: VisualSlide[]
}

type InfographicPanelKind =
  | 'text'
  | 'metric'
  | 'timeline'
  | 'comparison'
  | 'process'
  | 'chart'

interface InfographicPanel {
  kind: InfographicPanelKind
  heading: string
  body: string
  value: string
  citations: string[]
}

export interface InfographicVisualDocument {
  schema_version: 1
  artifact_type: 'infographic'
  title: string
  orientation: 'portrait' | 'landscape' | 'square'
  panels: InfographicPanel[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function stringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isVisualSlide(value: unknown): value is VisualSlide {
  return isRecord(value)
    && typeof value.title === 'string'
    && stringArray(value.bullets)
    && typeof value.speaker_notes === 'string'
    && typeof value.visual_direction === 'string'
    && stringArray(value.citations)
}

export function isSlideDeckDocument(value: unknown): value is SlideDeckVisualDocument {
  return isRecord(value)
    && value.schema_version === 1
    && value.artifact_type === 'slide_deck'
    && typeof value.title === 'string'
    && typeof value.audience === 'string'
    && Array.isArray(value.slides)
    && value.slides.length > 0
    && value.slides.every(isVisualSlide)
}

const INFOGRAPHIC_KINDS = new Set<InfographicPanelKind>([
  'text',
  'metric',
  'timeline',
  'comparison',
  'process',
  'chart',
])

function isInfographicPanel(value: unknown): value is InfographicPanel {
  return isRecord(value)
    && typeof value.kind === 'string'
    && INFOGRAPHIC_KINDS.has(value.kind as InfographicPanelKind)
    && typeof value.heading === 'string'
    && typeof value.body === 'string'
    && typeof value.value === 'string'
    && stringArray(value.citations)
}

export function isInfographicDocument(value: unknown): value is InfographicVisualDocument {
  return isRecord(value)
    && value.schema_version === 1
    && value.artifact_type === 'infographic'
    && typeof value.title === 'string'
    && ['portrait', 'landscape', 'square'].includes(String(value.orientation))
    && Array.isArray(value.panels)
    && value.panels.length > 0
    && value.panels.every(isInfographicPanel)
}

export function SlideDeckViewer({ document }: { document: SlideDeckVisualDocument }) {
  const [index, setIndex] = useState(0)
  const [showNotes, setShowNotes] = useState(false)
  const totalSlides = document.slides.length + 1
  const slide = index === 0 ? null : document.slides[index - 1]

  useEffect(() => {
    setIndex(0)
    setShowNotes(false)
  }, [document])

  const move = (offset: number) => {
    setIndex((current) => Math.min(totalSlides - 1, Math.max(0, current + offset)))
    setShowNotes(false)
  }

  return (
    <section
      role="region"
      aria-label="Slide deck"
      tabIndex={0}
      className="grid min-w-0 gap-3 outline-none focus-visible:ring-2 focus-visible:ring-ring lg:grid-cols-[10rem_minmax(0,1fr)]"
      onKeyDown={(event) => {
        if (event.key === 'ArrowLeft') move(-1)
        if (event.key === 'ArrowRight') move(1)
      }}
    >
      <div className="flex gap-2 overflow-x-auto pb-1 lg:max-h-[32rem] lg:flex-col lg:overflow-y-auto lg:pr-1">
        <button
          type="button"
          aria-label={`Open slide 1: ${document.title}`}
          aria-current={index === 0 ? 'true' : undefined}
          className={cn(
            'w-36 shrink-0 border-l-2 bg-muted/30 px-2 py-2 text-left transition-colors lg:w-full',
            index === 0
              ? 'border-l-[var(--dn-status-info)] bg-muted text-foreground'
              : 'border-l-transparent text-muted-foreground hover:bg-muted/60',
          )}
          onClick={() => {
            setIndex(0)
            setShowNotes(false)
          }}
        >
          <span className="block text-[0.68rem] font-semibold uppercase tracking-normal">01</span>
          <span className="mt-1 block line-clamp-2 text-xs font-medium leading-4">
            {document.title}
          </span>
        </button>
        {document.slides.map((item, slideIndex) => (
          <button
            key={`${slideIndex}-${item.title}`}
            type="button"
            aria-label={`Open slide ${slideIndex + 2}: ${item.title}`}
            aria-current={slideIndex + 1 === index ? 'true' : undefined}
            className={cn(
              'w-36 shrink-0 border-l-2 bg-muted/30 px-2 py-2 text-left transition-colors lg:w-full',
              slideIndex + 1 === index
                ? 'border-l-[var(--dn-status-info)] bg-muted text-foreground'
                : 'border-l-transparent text-muted-foreground hover:bg-muted/60',
            )}
            onClick={() => {
              setIndex(slideIndex + 1)
              setShowNotes(false)
            }}
          >
            <span className="block text-[0.68rem] font-semibold uppercase tracking-normal">
              {String(slideIndex + 2).padStart(2, '0')}
            </span>
            <span className="mt-1 block line-clamp-2 text-xs font-medium leading-4">
              {item.title}
            </span>
          </button>
        ))}
      </div>

      <div className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-semibold">{document.title}</div>
            <div className="text-xs text-muted-foreground">
              Slide {index + 1} of {totalSlides}
              {document.audience ? ` · ${document.audience}` : ''}
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-8 w-8"
              aria-label="Previous slide"
              title="Previous slide"
              disabled={index === 0}
              onClick={() => move(-1)}
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-8 w-8"
              aria-label="Next slide"
              title="Next slide"
              disabled={index === totalSlides - 1}
              onClick={() => move(1)}
            >
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </div>

        {slide === null ? (
          <article className="aspect-video min-h-0 overflow-hidden border border-[var(--dn-artifact-line)] bg-[var(--dn-artifact-canvas)] text-[var(--dn-artifact-ink)] shadow-sm [container-type:inline-size]">
            <div className="grid h-full grid-cols-[0.65rem_minmax(0,1fr)] gap-[clamp(1rem,4cqi,2.5rem)] p-[clamp(1rem,5cqi,3rem)]">
              <div className="rounded-full bg-[var(--dn-status-info)]" aria-hidden="true" />
              <div className="flex min-w-0 flex-col justify-center">
                <h3 className="line-clamp-3 text-[clamp(1.35rem,5cqi,3rem)] font-semibold leading-tight">
                  {document.title}
                </h3>
                {document.audience && (
                  <div className="mt-[clamp(1rem,5cqi,3rem)] text-[clamp(0.75rem,2.2cqi,1.2rem)] text-[var(--dn-artifact-muted)]">
                    Prepared for {document.audience}
                  </div>
                )}
                <div className="mt-auto text-[clamp(0.55rem,1.4cqi,0.75rem)] font-semibold uppercase tracking-normal text-[var(--dn-artifact-muted)]">
                  Deeper Notebook / Evidence Studio
                </div>
              </div>
            </div>
          </article>
        ) : (
          <article className="aspect-video min-h-0 overflow-hidden border border-[var(--dn-artifact-line)] bg-[var(--dn-artifact-panel)] text-[var(--dn-artifact-ink)] shadow-sm">
            <div className="h-2 bg-[var(--dn-status-info)]" />
            <div className="grid h-[calc(100%_-_0.5rem)] grid-rows-[auto_minmax(0,1fr)_auto] gap-3 p-[clamp(1rem,4cqi,2.5rem)] [container-type:inline-size]">
              <h3 className="line-clamp-2 text-[clamp(1rem,4cqi,2rem)] font-semibold leading-tight">
                {slide.title}
              </h3>
              <div className="grid min-h-0 gap-4 md:grid-cols-[minmax(0,1fr)_minmax(9rem,0.35fr)]">
                <ul className="min-h-0 space-y-[clamp(0.3rem,1.4cqi,0.8rem)] overflow-y-auto pr-2 text-[clamp(0.72rem,2.4cqi,1.15rem)] leading-relaxed">
                  {slide.bullets.map((bullet, bulletIndex) => (
                    <li key={`${bulletIndex}-${bullet}`} className="flex gap-2">
                      <span className="mt-[0.55em] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--dn-status-info)]" aria-hidden="true" />
                      <span>{bullet}</span>
                    </li>
                  ))}
                </ul>
                {slide.visual_direction && (
                  <div className="hidden min-h-0 overflow-y-auto border-l border-[var(--dn-artifact-line)] pl-4 md:block">
                    <div className="text-[0.62rem] font-semibold uppercase tracking-normal text-[var(--dn-status-info)]">
                      Visual direction
                    </div>
                    <div className="mt-2 text-[clamp(0.68rem,1.8cqi,0.92rem)] leading-relaxed text-[var(--dn-artifact-muted)]">
                      {slide.visual_direction}
                    </div>
                  </div>
                )}
              </div>
              <div className="flex min-h-5 items-end justify-between gap-3 text-[0.68rem] text-[var(--dn-artifact-muted)]">
                <div className="flex flex-wrap gap-1">
                  {slide.citations.map((citation) => (
                    <span key={citation}>{citation}</span>
                  ))}
                </div>
                <span>{index}/{document.slides.length}</span>
              </div>
            </div>
          </article>
        )}

        {slide && (slide.speaker_notes || slide.visual_direction) && (
          <div className="border-l-2 border-l-[var(--dn-artifact-line)] bg-muted/30 px-3 py-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-1 text-xs"
              aria-label={showNotes ? 'Hide speaker notes' : 'Show speaker notes'}
              onClick={() => setShowNotes((current) => !current)}
            >
              <StickyNote className="h-3.5 w-3.5" aria-hidden="true" />
              {showNotes ? 'Hide notes' : 'Speaker notes'}
            </Button>
            {showNotes && (
              <div className="mt-2 grid gap-3 text-sm leading-6 text-muted-foreground md:grid-cols-2">
                {slide.speaker_notes && (
                  <div>
                    <div className="text-xs font-semibold text-foreground">Notes</div>
                    <div className="mt-1">{slide.speaker_notes}</div>
                  </div>
                )}
                {slide.visual_direction && (
                  <div>
                    <div className="text-xs font-semibold text-foreground">Visual direction</div>
                    <div className="mt-1">{slide.visual_direction}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

const PANEL_STYLES: Record<InfographicPanelKind, string> = {
  text: 'border-t-[var(--dn-status-info)]',
  metric: 'border-t-[var(--dn-status-success)]',
  timeline: 'border-t-[var(--dn-status-info)]',
  comparison: 'border-t-[var(--dn-status-warning)]',
  process: 'border-t-[var(--dn-status-info)]',
  chart: 'border-t-[var(--dn-status-success)]',
}

export function InfographicViewer({ document }: { document: InfographicVisualDocument }) {
  return (
    <figure
      aria-label={document.title}
      data-orientation={document.orientation}
      className={cn(
        'mx-auto w-full overflow-hidden border border-[var(--dn-artifact-line)] bg-[var(--dn-artifact-canvas)] p-4 text-[var(--dn-artifact-ink)] shadow-sm sm:p-6',
        document.orientation === 'portrait' && 'max-w-2xl',
        document.orientation === 'square' && 'max-w-3xl',
        document.orientation === 'landscape' && 'max-w-5xl',
      )}
    >
      <div className="border-t-4 border-t-[var(--dn-status-info)] pt-4">
        <h3 className="text-xl font-semibold leading-tight sm:text-2xl">{document.title}</h3>
        <div className="mt-2 text-[0.68rem] font-semibold uppercase tracking-normal text-[var(--dn-artifact-muted)]">
          Evidence Studio · Source-grounded visual
        </div>
      </div>
      <div
        className={cn(
          'mt-5 grid gap-3',
          document.orientation !== 'portrait' && 'sm:grid-cols-2',
        )}
      >
        {document.panels.map((panel, index) => (
          <section
            key={`${index}-${panel.heading}`}
            className={cn('min-h-40 border border-[var(--dn-artifact-line)] border-t-4 bg-[var(--dn-artifact-panel)] p-4', PANEL_STYLES[panel.kind])}
          >
            <div className="flex items-start justify-between gap-2">
              <Badge variant="outline" className="rounded-sm text-[0.62rem] capitalize">
                {panel.kind}
              </Badge>
              <span className="text-[0.68rem] font-semibold text-[var(--dn-artifact-muted)]">
                {String(index + 1).padStart(2, '0')}
              </span>
            </div>
            <h4 className="mt-3 text-base font-semibold leading-tight">{panel.heading}</h4>
            {panel.value && (
              <div className="mt-3 break-words text-3xl font-semibold text-[var(--dn-status-success)]">
                {panel.value}
              </div>
            )}
            {panel.body && (
              <div className="mt-3 text-sm leading-6 text-[var(--dn-artifact-muted)]">{panel.body}</div>
            )}
            {panel.citations.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-1 text-[0.68rem] text-[var(--dn-artifact-muted)]">
                {panel.citations.map((citation) => (
                  <span key={citation}>{citation}</span>
                ))}
              </div>
            )}
          </section>
        ))}
      </div>
      <figcaption className="mt-4 text-[0.68rem] text-[var(--dn-artifact-muted)]">
        {document.panels.length} {document.panels.length === 1 ? 'panel' : 'panels'} · {document.orientation}
      </figcaption>
    </figure>
  )
}

/**
 * v0.7.39 — Lightweight virtualization primitive on top of
 * @tanstack/react-virtual.
 *
 * Two flavors:
 *
 *   <VirtualizedList>           — fixed-size rows (cheap; preferred)
 *   <VirtualizedListAuto>       — dynamic-size rows (measureElement
 *                                 round-trip, slightly more expensive
 *                                 but handles variable content)
 *
 * Both render only the rows currently in the viewport plus a small
 * overscan buffer. For a 5000-source list that previously rendered
 * 5000 row components on every parent state change, this drops to
 * ~30 (visible + overscan).
 *
 * Wraps in a `role="rowgroup"` div so screen readers see the same
 * semantic grouping a real `<tbody>` would expose. Each row gets
 * `role="row"`. Items can stay as `<tr>` / `<div>` / whatever —
 * the wrapper doesn't impose a tag.
 *
 * For ROW-counts below the virtualization break-even (~100 rows on
 * most hardware) just render the list directly — the overhead of the
 * virtualizer is real (event listeners, scroll math) and isn't worth
 * it for small N. Callers should gate on `items.length >= threshold`
 * themselves to keep the choice explicit.
 */
'use client'

import { useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'

import { cn } from '@/lib/utils'

interface VirtualizedListProps<T> {
  items: T[]
  estimateSize: number
  renderItem: (item: T, index: number) => React.ReactNode
  /** Tailwind / CSS for the outer scroll container. Must have a height
   * constraint (e.g. h-[60vh], flex-1 inside a flex column). */
  className?: string
  /** Number of rows to render outside the viewport on each side. */
  overscan?: number
  /** Stable id extractor; uses array index by default. */
  getItemKey?: (item: T, index: number) => string | number
  // v0.8.101 — the `containerAs?: 'div' | 'tbody'` escape hatch was removed.
  // It rendered <tbody> inside this component's hardcoded <div> scroll parent
  // AND wrapped each row in a <div> inside that <tbody> (which may only hold
  // <tr>), so React warned "In HTML, <tbody> cannot be a child of <div>. This
  // will cause a hydration error." on every test run. Nothing consumed it —
  // SourcesColumn, the only caller in the app, uses VirtualizedListAuto with
  // no containerAs — and its one test asserted merely that a <tbody> existed,
  // never that the nesting was valid, which is why it survived.
  //
  // In-table virtualization needs more than an element swap (the row wrappers
  // are absolutely positioned, which table layout does not honour), so a real
  // implementation should be designed against an actual table consumer rather
  // than left as a broken stub. Removed rather than "fixed" blind.
}

export function VirtualizedList<T>({
  items,
  estimateSize,
  renderItem,
  className,
  overscan = 5,
  getItemKey,
}: VirtualizedListProps<T>) {
  'use no memo'

  const parentRef = useRef<HTMLDivElement>(null)

  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Virtual intentionally returns non-memoizable helpers; this wrapper is the isolated virtualization boundary.
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimateSize,
    overscan,
    getItemKey: getItemKey
      ? (i) => getItemKey(items[i], i)
      : undefined,
  })

  const virtualItems = virtualizer.getVirtualItems()
  const totalSize = virtualizer.getTotalSize()

  return (
    <div ref={parentRef} className={cn('overflow-auto', className)}>
      <div
        role="rowgroup"
        style={{
          height: `${totalSize}px`,
          position: 'relative',
        }}
      >
        {virtualItems.map((virtualRow) => (
          <div
            key={virtualRow.key}
            role="row"
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: `${virtualRow.size}px`,
              transform: `translateY(${virtualRow.start}px)`,
            }}
          >
            {renderItem(items[virtualRow.index], virtualRow.index)}
          </div>
        ))}
      </div>
    </div>
  )
}


interface VirtualizedListAutoProps<T> {
  items: T[]
  /** Initial size guess for rows whose actual size hasn't been measured
   * yet. Closer-to-real means fewer scroll jumps on first paint. */
  estimateSize: number
  renderItem: (item: T, index: number) => React.ReactNode
  className?: string
  overscan?: number
  getItemKey?: (item: T, index: number) => string | number
  /** Forwarded to the scroll container's `onScroll`. Lets callers wire
   * infinite-scroll loaders (load more when near bottom) into the
   * same element the virtualizer is using as its scroll surface. */
  onScroll?: React.UIEventHandler<HTMLDivElement>
  /** Optional trailing element rendered AFTER the virtualized rows
   * (e.g. a "Loading more..." spinner during infinite scroll). Not
   * virtualized; always rendered when present. */
  footer?: React.ReactNode
}

/**
 * Auto-sizing variant for lists where row heights vary at runtime
 * (markdown messages, expandable cards, etc.). Uses ResizeObserver via
 * react-virtual's `measureElement` to get true sizes. Slightly heavier
 * than the fixed variant; prefer the fixed variant when you can.
 */
export function VirtualizedListAuto<T>({
  items,
  estimateSize,
  renderItem,
  className,
  overscan = 5,
  getItemKey,
  onScroll,
  footer,
}: VirtualizedListAutoProps<T>) {
  'use no memo'

  const parentRef = useRef<HTMLDivElement>(null)

  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Virtual intentionally returns non-memoizable helpers; this wrapper is the isolated virtualization boundary.
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimateSize,
    overscan,
    getItemKey: getItemKey
      ? (i) => getItemKey(items[i], i)
      : undefined,
  })

  const virtualItems = virtualizer.getVirtualItems()
  const totalSize = virtualizer.getTotalSize()

  return (
    <div
      ref={parentRef}
      onScroll={onScroll}
      className={cn('overflow-auto', className)}
    >
      <div
        role="rowgroup"
        style={{
          height: `${totalSize}px`,
          position: 'relative',
        }}
      >
        {virtualItems.map((virtualRow) => (
          <div
            key={virtualRow.key}
            ref={virtualizer.measureElement}
            data-index={virtualRow.index}
            role="row"
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${virtualRow.start}px)`,
            }}
          >
            {renderItem(items[virtualRow.index], virtualRow.index)}
          </div>
        ))}
      </div>
      {footer}
    </div>
  )
}

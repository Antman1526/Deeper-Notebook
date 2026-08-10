'use client'

import * as React from 'react'

import { cn } from '@/lib/utils'

import { FolioTab, type FolioTabItem } from './FolioTab'

export interface FolioIndexProps {
  label: string
  items: readonly FolioTabItem[]
  value: string
  onValueChange(value: string): void
}

function nextIndex(current: number, length: number, direction: 1 | -1): number {
  return (current + direction + length) % length
}

/** Controlled notebook index with roving focus and standard tab-key behavior. */
export const FolioIndex = React.forwardRef<HTMLElement, FolioIndexProps>(
  function FolioIndex({ label, items, value, onValueChange }, ref) {
    const tabRefs = React.useRef<Array<HTMLButtonElement | null>>([])
    const generatedId = React.useId()
    const activeIndex = items.findIndex(item => item.id === value)

    const focusIndex = (index: number) => {
      const item = items[index]
      if (!item) return
      onValueChange(item.id)
      tabRefs.current[index]?.focus()
    }

    const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
      if (items.length === 0) return

      let targetIndex: number | null = null
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
        targetIndex = nextIndex(index, items.length, 1)
      } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
        targetIndex = nextIndex(index, items.length, -1)
      } else if (event.key === 'Home') {
        targetIndex = 0
      } else if (event.key === 'End') {
        targetIndex = items.length - 1
      }

      if (targetIndex === null) return
      event.preventDefault()
      focusIndex(targetIndex)
    }

    return (
      <nav
        ref={ref}
        aria-label={label}
        data-dn-folio-index="true"
        className={cn('dn-folio-index')}
      >
        <div
          id={`${generatedId}-list`}
          role="tablist"
          aria-label={label}
          aria-orientation="horizontal"
          data-dn-folio-tablist="true"
          className="dn-folio-tablist"
        >
          {items.map((item, index) => (
            <FolioTab
              key={item.id}
              ref={element => {
                tabRefs.current[index] = element
              }}
              id={`${generatedId}-${item.id}`}
              label={item.label}
              badge={item.badge}
              selected={activeIndex < 0 ? index === 0 : item.id === value}
              onActivate={() => onValueChange(item.id)}
              onKeyDown={event => handleKeyDown(event, index)}
            />
          ))}
        </div>
      </nav>
    )
  },
)

FolioIndex.displayName = 'FolioIndex'

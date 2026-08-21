'use client'

import { ImageOff, MoreHorizontal, RefreshCw, Trash2 } from 'lucide-react'
import { useRef, useState } from 'react'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export type SourceCoverActionsProps = {
  title: string
  pending: boolean
  visualsDisabled: boolean
  onRefresh?: () => void
  onRemove?: () => void
  onDelete?: () => void
}

export function SourceCoverActions({
  title,
  pending,
  visualsDisabled,
  onRefresh,
  onRemove,
  onDelete,
}: SourceCoverActionsProps) {
  const [open, setOpen] = useState(false)
  const activationRef = useRef<'pointer' | 'keyboard' | null>(null)

  if (!onRefresh && !onRemove && !onDelete) return null

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="dn-source-cover__actions-trigger"
          aria-label={`Actions for ${title}`}
          onPointerDown={() => {
            activationRef.current = 'pointer'
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') activationRef.current = 'keyboard'
          }}
          onClick={() => {
            if (activationRef.current) {
              activationRef.current = null
              return
            }
            setOpen(current => !current)
          }}
        >
          <MoreHorizontal aria-hidden="true" className="h-4 w-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        {onRefresh && !visualsDisabled ? (
          <DropdownMenuItem disabled={pending} onSelect={onRefresh}>
            <RefreshCw aria-hidden="true" className="h-4 w-4" />
            Refresh visual
          </DropdownMenuItem>
        ) : null}
        {onRemove && !visualsDisabled ? (
          <DropdownMenuItem disabled={pending} onSelect={onRemove}>
            <ImageOff aria-hidden="true" className="h-4 w-4" />
            Remove visual
          </DropdownMenuItem>
        ) : null}
        {onDelete ? (
          <DropdownMenuItem
            onSelect={onDelete}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 aria-hidden="true" className="h-4 w-4" />
            Delete source
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

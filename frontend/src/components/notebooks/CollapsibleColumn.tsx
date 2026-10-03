'use client'

import { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ChevronLeft, LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'

interface CollapsibleColumnProps {
  isCollapsed: boolean
  onToggle: () => void
  collapsedIcon: LucideIcon
  collapsedLabel: string
  children: ReactNode
}

export function CollapsibleColumn({
  isCollapsed,
  onToggle,
  collapsedIcon: CollapsedIcon,
  collapsedLabel,
  children,
}: CollapsibleColumnProps) {
  const { t } = useTranslation()
  const isCJK = /[\u4e00-\u9fa5\u3040-\u30ff\uac00-\ud7af]/.test(collapsedLabel);

  if (isCollapsed) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={onToggle}
              className={cn(
                'flex flex-col items-center justify-center gap-3',
                'w-12 h-full min-h-0',
                'border rounded-lg',
                'bg-card hover:bg-accent/50',
                // v0.8.130 — named transition (UI audit Phase 1)
                'transition-colors duration-150',
                'cursor-pointer group',
                'py-6'
              )}
              aria-label={t('notebooks.collapsibleColumn.expand', { label: collapsedLabel })}
            >
              <CollapsedIcon className="h-5 w-5 text-muted-foreground group-hover:text-foreground transition-colors flex-shrink-0" />
              <div
                className="text-xs font-medium text-muted-foreground group-hover:text-foreground transition-colors whitespace-nowrap"
                style={{ writingMode: 'vertical-rl', transform: isCJK ? 'none' : 'rotate(180deg)', textOrientation: 'mixed' }}
              >
                {collapsedLabel}
              </div>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">
            <p>{t('notebooks.collapsibleColumn.expand', { label: collapsedLabel })}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return (
    <div className="h-full min-h-0">
      {children}
    </div>
  )
}

// Factory function to create a collapse button for card headers
export function createCollapseButton(onToggle: () => void, label: string) {
  return <CollapseButton onToggle={onToggle} label={label} />
}

function CollapseButton({ onToggle, label }: { onToggle: () => void; label: string }) {
  const { t } = useTranslation()
  return (
    <div className="hidden lg:block">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={(e) => {
                e.stopPropagation()
                onToggle()
              }}
              className="h-7 w-7 hover:bg-accent"
              aria-label={t('notebooks.collapsibleColumn.collapse', { label })}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>{t('notebooks.collapsibleColumn.collapse', { label })}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  )
}

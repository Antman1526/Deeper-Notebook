import { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
  action?: React.ReactNode
  className?: string
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={`relative flex flex-col items-center justify-center text-center py-12 px-4 ${className || ''}`}>
      {/* Ambient aura glow */}
      <div className="relative mb-4 flex items-center justify-center">
        <div className="relative flex h-14 w-14 items-center justify-center rounded-xl border bg-muted/30">
          {/* v0.8.130 — no hover/press scale (UI audit Phase 1) */}
          <Icon className="h-7 w-7 text-primary/80" />
        </div>
      </div>
      <h3 className="text-base font-semibold text-foreground tracking-tight mb-1.5">{title}</h3>
      <p className="text-xs text-muted-foreground max-w-sm mx-auto leading-relaxed mb-4">{description}</p>
      {action && (
        <div className="mt-1">
          {action}
        </div>
      )}
    </div>
  )
}

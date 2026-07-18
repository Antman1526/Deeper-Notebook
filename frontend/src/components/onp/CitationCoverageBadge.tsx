import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

function citationLabel(citationCount: number): string {
  if (citationCount === 0) return 'No citations'
  if (citationCount === 1) return '1 citation'
  return `${citationCount} citations`
}

export function CitationCoverageBadge({ citationCount }: { citationCount: number }) {
  const hasCitations = citationCount > 0

  return (
    <Badge
      variant="outline"
      className={cn(
        'text-[0.68rem]',
        hasCitations
          ? 'border-[var(--onp-evidence)] text-[var(--onp-evidence)]'
          : 'border-[var(--onp-warning)] text-[var(--onp-warning)]',
      )}
    >
      {citationLabel(citationCount)}
    </Badge>
  )
}

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
          ? 'border-[var(--dn-evidence)] text-[var(--dn-evidence)]'
          : 'border-[var(--dn-warning)] text-[var(--dn-warning)]',
      )}
    >
      {citationLabel(citationCount)}
    </Badge>
  )
}

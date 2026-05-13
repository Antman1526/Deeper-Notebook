/**
 * ReasoningSlotCard — informational panel explaining the v0.5 Reasoning slot.
 *
 * Reference shadow-layer component (see ./README.md):
 *   - uses shadcn primitives + onp tokens, no raw colors
 *   - imported from a single upstream edit (one line in the page file)
 *   - self-contained, no upstream component edits
 */

import { Sparkles } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface ReasoningSlotCardProps {
  /** Optional model name currently assigned to the reasoning slot. */
  assignedModel?: string | null
}

export function ReasoningSlotCard({ assignedModel }: ReasoningSlotCardProps) {
  return (
    <Card
      className="border"
      style={{
        background: 'var(--onp-info-soft)',
        boxShadow: 'var(--onp-elevation-low)',
      }}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles
            className="h-4 w-4"
            style={{ color: 'var(--primary)' }}
            aria-hidden="true"
          />
          Reasoning model
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p
          className="text-sm leading-relaxed"
          style={{ color: 'var(--muted-foreground)' }}
        >
          For hard questions and multi-step analysis. Distinct from the chat
          model so your casual conversation stays fast — only routed here when
          you explicitly ask the assistant to <em>think hard</em> about
          something.
        </p>
        {assignedModel && (
          <p className="text-sm" style={{ color: 'var(--foreground)' }}>
            Currently using <strong>{assignedModel}</strong>.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

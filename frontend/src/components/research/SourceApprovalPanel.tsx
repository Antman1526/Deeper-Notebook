'use client'

import { useEffect, useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import type { ResearchCandidate } from '@/lib/api/research'

import { EvidenceReceipt } from './EvidenceReceipt'

export function SourceApprovalPanel({ candidates, disabled, onApprove }: { candidates: ResearchCandidate[]; disabled?: boolean; onApprove: (accepted: string[]) => void }) {
  const pending = useMemo(
    () => candidates.filter((candidate) => candidate.decision === 'pending'),
    [candidates],
  )
  const [accepted, setAccepted] = useState<string[]>([])
  useEffect(() => setAccepted(pending.map((candidate) => candidate.candidate_id)), [pending])
  if (!pending.length) return null
  const toggle = (candidateId: string) => setAccepted((current) => current.includes(candidateId) ? current.filter((value) => value !== candidateId) : [...current, candidateId])
  // v0.8.130 — in a narrow column the panel drops its own frame (it already sits in the
  // research band) and candidate rows tighten, so the evidence receipt has room.
  // The checkbox is a fixed 16px on the title's first line: in a stretching flex label
  // it grew to the label's full height and was drawn as a large square.
  return (
    <section aria-label="Source approval" className="rounded-md border bg-background p-4 @max-md:border-0 @max-md:bg-transparent @max-md:p-0">
      <h2 className="text-sm font-semibold">Approve sources before import</h2><p className="mt-1 text-xs text-muted-foreground">Only selected public URLs will be fetched. Unselected candidates remain rejected in the local audit trail.</p>
      <div className="mt-3 space-y-2">{pending.map((candidate) => <div key={candidate.candidate_id} className="rounded-md border p-3 text-sm @max-md:p-2.5"><label className="flex cursor-pointer items-start gap-3"><input type="checkbox" data-dn-checkbox-on-first-line="" className="mt-0.5 size-4 shrink-0 accent-primary" checked={accepted.includes(candidate.candidate_id)} onChange={() => toggle(candidate.candidate_id)} /><span className="min-w-0"><span className="block font-medium">{candidate.title ?? candidate.domain}</span><span className="block truncate text-xs text-muted-foreground">{candidate.domain} · {candidate.url}</span>{candidate.snippet ? <span className="mt-1 block text-xs text-muted-foreground">{candidate.snippet}</span> : null}</span></label><EvidenceReceipt evidence={candidate.evidence} /></div>)}</div>
      <Button type="button" className="mt-3" disabled={disabled} onClick={() => onApprove(accepted)}>Approve selected sources</Button>
    </section>
  )
}

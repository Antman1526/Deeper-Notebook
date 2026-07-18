'use client'

import { useEffect, useState } from 'react'
import { LoaderCircle, RotateCcw, Square } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useResearchRun, useResearchRunActions } from '@/lib/hooks/use-research-run'
import { ContradictionTable } from './ContradictionTable'
import { ResearchPlanPanel } from './ResearchPlanPanel'
import { SourceApprovalPanel } from './SourceApprovalPanel'

function storageKey(notebookId: string) { return `onp-research-run:${notebookId}` }

export function ResearchRunWorkspace({ notebookId }: { notebookId: string }) {
  const [runId, setRunId] = useState<string | null>(null)
  const [objective, setObjective] = useState('')
  useEffect(() => setRunId(window.localStorage.getItem(storageKey(notebookId))), [notebookId])
  const run = useResearchRun(notebookId, runId)
  const actions = useResearchRunActions(notebookId, runId)
  const start = async () => {
    const created = await actions.create.mutateAsync(objective.trim())
    window.localStorage.setItem(storageKey(notebookId), created.id)
    setRunId(created.id)
    setObjective('')
  }
  return <section className="mb-5 border-y bg-muted/20 px-4 py-4" aria-label="Guided research workspace"><div className="mx-auto max-w-7xl space-y-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-base font-semibold">Guided research</h2><p className="text-sm text-muted-foreground">Discover sources only when you explicitly start, then approve each source before import.</p></div>{run.data ? <div className="flex gap-2"><Button type="button" variant="outline" size="sm" disabled={actions.resume.isPending || run.data.cancelled} onClick={() => void actions.resume.mutateAsync()}><RotateCcw className="mr-2 h-4 w-4" />Resume</Button><Button type="button" variant="outline" size="sm" disabled={actions.cancel.isPending || run.data.cancelled} onClick={() => void actions.cancel.mutateAsync()}><Square className="mr-2 h-4 w-4" />Cancel</Button></div> : null}</div>{!runId ? <div className="flex flex-col gap-2 sm:flex-row"><Input aria-label="Research objective" value={objective} onChange={(event) => setObjective(event.target.value)} placeholder="What do you want to investigate?" /><Button type="button" disabled={!objective.trim() || actions.create.isPending} onClick={() => void start()}>{actions.create.isPending ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}Start research</Button></div> : null}{run.isLoading ? <p className="text-sm text-muted-foreground">Restoring the last research run…</p> : null}{run.isError ? <p role="alert" className="text-sm text-destructive">The saved research run could not be restored. It has not been deleted.</p> : null}{run.data ? <><ResearchPlanPanel run={run.data} /><SourceApprovalPanel candidates={run.data.candidates} disabled={actions.approve.isPending || run.data.cancelled} onApprove={(accepted) => void actions.approve.mutateAsync(accepted)} /><ContradictionTable comparison={run.data.comparison} />{run.data.errors.length ? <ul className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">{run.data.errors.map((error) => <li key={error}>{error}</li>)}</ul> : null}</> : null}</div></section>
}

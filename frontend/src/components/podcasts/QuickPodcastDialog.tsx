'use client'

import { useEffect, useState } from 'react'

import { podcastsApi } from '@/lib/api/podcasts'
import type { PodcastReadiness } from '@/lib/types/podcasts'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

/**
 * The first Quick Podcast gate. It is read-only: rendering and cancellation
 * only request readiness and clear transient state. Production confirmation is
 * deliberately withheld until the fingerprint-checked submit API is present.
 */
export function QuickPodcastDialog() {
  const isOpen = usePodcastStudioStore((state) => state.isOpen)
  const destination = usePodcastStudioStore((state) => state.destination)
  const selections = usePodcastStudioStore((state) => state.selections)
  const dismiss = usePodcastStudioStore((state) => state.dismiss)
  const [readiness, setReadiness] = useState<PodcastReadiness | null>(null)
  const [error, setError] = useState<string | null>(null)
  const open = isOpen && destination === 'quick'

  useEffect(() => {
    if (!open || selections.length === 0) {
      setReadiness(null)
      setError(null)
      return
    }
    let current = true
    setReadiness(null)
    setError(null)
    void podcastsApi.getPodcastReadiness(selections).then(
      (result) => current && setReadiness(result),
      () => current && setError('Podcast readiness is unavailable. No production was started.'),
    )
    return () => { current = false }
  }, [open, selections])

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && dismiss()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Review selection</DialogTitle>
          <DialogDescription>
            Podcast creation is optional. This step reads a temporary preview and does not start a model or create an episode.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4" aria-busy={readiness === null && error === null}>
          <section aria-labelledby="quick-podcast-research-set">
            <h2 id="quick-podcast-research-set" className="text-sm font-semibold">Research set</h2>
            {readiness ? (
              <ul className="mt-2 space-y-2" aria-label="Selected sources">
                {readiness.preview.entries.map((entry) => (
                  <li key={`${entry.stableId}:${entry.revisionId ?? 'current'}`} className="flex justify-between gap-3 text-sm">
                    <span>{entry.title}</span>
                    <span className="text-muted-foreground">{entry.state}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="mt-2 text-sm text-muted-foreground">{error ?? 'Checking local readiness…'}</p>}
          </section>
          <section aria-labelledby="quick-podcast-policy">
            <h2 id="quick-podcast-policy" className="text-sm font-semibold">Production policy</h2>
            <p className="mt-1 text-sm text-muted-foreground">Strict local evidence policy · Outline storyboard review</p>
          </section>
          {readiness?.blockedReasons.length ? (
            <p role="status" className="text-sm text-destructive">
              {readiness.blockedReasons.join(', ')}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={dismiss}>Cancel</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

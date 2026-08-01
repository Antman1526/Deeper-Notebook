'use client'

import { useMemo, useState } from 'react'

import { EpisodeCard } from '@/components/podcasts/EpisodeCard'
import { Button } from '@/components/ui/button'
import type { PodcastEpisode } from '@/lib/types/podcasts'

type LibraryGroup = 'Continue Production' | 'Ready to Review' | 'Completed' | 'Needs Attention'

export function groupEpisodesForLibrary(episodes: PodcastEpisode[]): Record<LibraryGroup, PodcastEpisode[]> {
  const groups: Record<LibraryGroup, PodcastEpisode[]> = {
    'Continue Production': [], 'Ready to Review': [], Completed: [], 'Needs Attention': [],
  }
  for (const episode of episodes) {
    if (episode.generation_stage === 'awaiting_review') groups['Ready to Review'].push(episode)
    else if (episode.job_status === 'completed') groups.Completed.push(episode)
    else if (episode.job_status === 'failed' || episode.job_status === 'error') groups['Needs Attention'].push(episode)
    else groups['Continue Production'].push(episode)
  }
  return groups
}

export function PodcastLibrary({ episodes, onDelete, onRetry }: {
  episodes: PodcastEpisode[]
  onDelete: (episodeId: string) => Promise<void> | void
  onRetry: (episodeId: string) => Promise<void> | void
}) {
  const [format, setFormat] = useState('all')
  const [profile, setProfile] = useState('all')
  const [stage, setStage] = useState('all')
  const profiles = useMemo(() => [...new Set(episodes.map(item => item.episode_profile?.name).filter(Boolean))] as string[], [episodes])
  const filtered = episodes.filter(episode => (
    (format === 'all' || episode.mode === format)
    && (profile === 'all' || episode.episode_profile?.name === profile)
    && (stage === 'all' || episode.generation_stage === stage)
  ))
  const groups = groupEpisodesForLibrary(filtered)
  return <section aria-label="Podcast Library" className="space-y-6">
    <div className="flex flex-wrap gap-3 rounded-md border p-3">
      <label className="grid gap-1 text-sm">Format<select aria-label="Format filter" value={format} onChange={event => setFormat(event.target.value)} className="h-9 rounded-md border bg-background px-2"><option value="all">All formats</option>{['deep_dive', 'brief', 'critique', 'debate'].map(value => <option key={value} value={value}>{value.replace('_', ' ')}</option>)}</select></label>
      <label className="grid gap-1 text-sm">Profile<select aria-label="Profile filter" value={profile} onChange={event => setProfile(event.target.value)} className="h-9 rounded-md border bg-background px-2"><option value="all">All profiles</option>{profiles.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <label className="grid gap-1 text-sm">Production stage<select aria-label="Production stage filter" value={stage} onChange={event => setStage(event.target.value)} className="h-9 rounded-md border bg-background px-2"><option value="all">All stages</option>{['awaiting_review', 'generating_outline', 'generating_transcript', 'generating_audio'].map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></label>
      <Button type="button" size="sm" variant="outline" disabled title="Evidence-state filters arrive in Phase 3">Evidence filters — Phase 3</Button>
    </div>
    {(Object.entries(groups) as Array<[LibraryGroup, PodcastEpisode[]]>).map(([title, items]) => items.length > 0 && <section key={title} aria-label={title} className="space-y-3"><h2 className="text-lg font-semibold">{title}</h2><div className="space-y-4">{items.map(episode => <EpisodeCard key={episode.id} episode={episode} onDelete={onDelete} onRetry={onRetry} />)}</div></section>)}
    {filtered.length === 0 && <p className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">No episodes match these production filters.</p>}
  </section>
}

'use client'

import { useMemo, useState } from 'react'

import { EpisodeCard } from '@/components/podcasts/EpisodeCard'
import { EpisodeLab } from '@/components/podcasts/EpisodeLab'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { PodcastEpisode } from '@/lib/types/podcasts'

export type LibraryGroup = 'Continue Production' | 'Ready to Review' | 'Completed' | 'Needs Attention'
/** Display keys for each group; the group names themselves stay stable identifiers. */
const LIBRARY_GROUP_LABEL_KEYS: Record<LibraryGroup, string> = {
  'Continue Production': 'podcasts.podcastLibrary.groupContinueProduction',
  'Ready to Review': 'podcasts.podcastLibrary.groupReadyToReview',
  Completed: 'podcasts.podcastLibrary.groupCompleted',
  'Needs Attention': 'podcasts.podcastLibrary.groupNeedsAttention',
}

const LIBRARY_FORMAT_LABEL_KEYS: Record<string, string> = {
  deep_dive: 'podcasts.podcastLibrary.formatDeepDive',
  brief: 'podcasts.podcastLibrary.formatBrief',
  critique: 'podcasts.podcastLibrary.formatCritique',
  debate: 'podcasts.podcastLibrary.formatDebate',
}

const LIBRARY_STAGE_LABEL_KEYS: Record<string, string> = {
  awaiting_review: 'podcasts.podcastLibrary.stageAwaitingReview',
  generating_outline: 'podcasts.podcastLibrary.stageGeneratingOutline',
  generating_transcript: 'podcasts.podcastLibrary.stageGeneratingTranscript',
  generating_audio: 'podcasts.podcastLibrary.stageGeneratingAudio',
  combining_audio: 'podcasts.podcastLibrary.stageCombiningAudio',
  completed: 'podcasts.podcastLibrary.stageCompleted',
  failed: 'podcasts.podcastLibrary.stageFailed',
  cancelled: 'podcasts.podcastLibrary.stageCancelled',
  running: 'podcasts.podcastLibrary.stageRunning',
  processing: 'podcasts.podcastLibrary.stageProcessing',
  pending: 'podcasts.podcastLibrary.stagePending',
  submitted: 'podcasts.podcastLibrary.stageSubmitted',
}

type LibraryDateFilter = 'all' | 'seven_days' | 'thirty_days' | 'older'
type LibraryAuthorityFilter = 'all' | 'app_owned' | 'external_read_only'

export interface LibraryFilters {
  format: string
  profile: string
  stage: string
  date: LibraryDateFilter
  authority: LibraryAuthorityFilter
}

const KNOWN_LIBRARY_STAGES = [
  'awaiting_review',
  'generating_outline',
  'generating_transcript',
  'generating_audio',
  'combining_audio',
  'completed',
  'failed',
  'cancelled',
  'running',
  'processing',
  'pending',
  'submitted',
] as const

function isSafeStageValue(value: string): boolean {
  return value.length <= 64 && /^[A-Za-z0-9][A-Za-z0-9:_-]*$/.test(value)
}

/**
 * Return a bounded stage vocabulary. Persisted stage strings are data, not
 * locators, so reject path-like values before they reach the filter UI.
 */
export function getLibraryStageOptions(episodes: PodcastEpisode[]): string[] {
  const discovered = episodes
    .map((episode) => episode.generation_stage)
    .filter((stage): stage is string => typeof stage === 'string' && stage.length > 0 && isSafeStageValue(stage))
  return [...new Set([...KNOWN_LIBRARY_STAGES, ...discovered])]
}

function productionStage(episode: PodcastEpisode): string | null {
  if (episode.generation_stage && isSafeStageValue(episode.generation_stage)) {
    return episode.generation_stage
  }

  const status = (episode.job_status ?? '').toLowerCase()
  if (status === 'completed') return 'completed'
  if (status === 'failed' || status === 'error') return 'failed'
  if (status === 'cancelled' || status === 'canceled') return 'cancelled'
  if (KNOWN_LIBRARY_STAGES.includes(status as (typeof KNOWN_LIBRARY_STAGES)[number])) return status
  return null
}

function isNeedsAttention(episode: PodcastEpisode): boolean {
  const status = (episode.job_status ?? '').toLowerCase()
  const stage = (episode.generation_stage ?? '').toLowerCase()
  return status === 'failed'
    || status === 'error'
    || status === 'cancelled'
    || status === 'canceled'
    || stage === 'failed'
    || stage === 'error'
    || stage === 'cancelled'
    || stage === 'canceled'
}

export function groupEpisodesForLibrary(episodes: PodcastEpisode[]): Record<LibraryGroup, PodcastEpisode[]> {
  const groups: Record<LibraryGroup, PodcastEpisode[]> = {
    'Continue Production': [], 'Ready to Review': [], Completed: [], 'Needs Attention': [],
  }
  for (const episode of episodes) {
    if (isNeedsAttention(episode)) groups['Needs Attention'].push(episode)
    else if (episode.generation_stage === 'awaiting_review') groups['Ready to Review'].push(episode)
    else if (episode.job_status === 'completed') groups.Completed.push(episode)
    else groups['Continue Production'].push(episode)
  }
  return groups
}

function isInDateFilter(created: string | null | undefined, date: LibraryDateFilter, now: Date): boolean {
  if (date === 'all') return true
  if (!created) return false
  const timestamp = Date.parse(created)
  if (!Number.isFinite(timestamp)) return false
  const ageInDays = (now.getTime() - timestamp) / 86_400_000
  if (date === 'seven_days') return ageInDays <= 7
  if (date === 'thirty_days') return ageInDays <= 30
  return ageInDays > 30
}

function hasAuthority(episode: PodcastEpisode, authority: LibraryAuthorityFilter): boolean {
  if (authority === 'all') return true
  return (episode.selection_summary?.authority_counts?.[authority] ?? 0) > 0
}

export function filterEpisodesForLibrary(
  episodes: PodcastEpisode[],
  filters: LibraryFilters,
  now = new Date(),
): PodcastEpisode[] {
  return episodes.filter((episode) => (
    (filters.format === 'all' || (episode.mode ?? 'deep_dive') === filters.format)
    && (filters.profile === 'all' || episode.episode_profile?.name === filters.profile)
    && (filters.stage === 'all' || productionStage(episode) === filters.stage)
    && isInDateFilter(episode.created, filters.date, now)
    && hasAuthority(episode, filters.authority)
  ))
}

export function PodcastLibrary({ episodes, onDelete, onRetry, onCancel, retrying, onCitationClick }: {
  episodes: PodcastEpisode[]
  onDelete: (episodeId: string) => Promise<void> | void
  onRetry: (episodeId: string) => Promise<void> | void
  onCancel?: (episodeId: string) => Promise<void> | void
  retrying?: boolean
  onCitationClick?: (citationId: string) => void
}) {
  const { t } = useTranslation()
  const [format, setFormat] = useState('all')
  const [profile, setProfile] = useState('all')
  const [stage, setStage] = useState('all')
  const [date, setDate] = useState<LibraryDateFilter>('all')
  const [authority, setAuthority] = useState<LibraryAuthorityFilter>('all')
  const [labEpisodeId, setLabEpisodeId] = useState<string | null>(null)
  const profiles = useMemo(() => [...new Set(episodes.map(item => item.episode_profile?.name).filter(Boolean))] as string[], [episodes])
  const stageOptions = useMemo(() => getLibraryStageOptions(episodes), [episodes])
  const filtered = filterEpisodesForLibrary(episodes, { format, profile, stage, date, authority })
  const groups = groupEpisodesForLibrary(filtered)
  const labEpisode = episodes.find((episode) => episode.id === labEpisodeId) ?? null
  return <section aria-label={t('podcasts.podcastLibrary.title')} className="space-y-6">
    <div className="flex flex-wrap gap-3 rounded-md border p-3">
      <label className="grid gap-1 text-sm">{t('podcasts.podcastLibrary.format')}<select aria-label={t('podcasts.podcastLibrary.formatFilter')} value={format} onChange={event => setFormat(event.target.value)} className="h-9 rounded-md border bg-background px-2"><option value="all">{t('podcasts.podcastLibrary.allFormats')}</option>{['deep_dive', 'brief', 'critique', 'debate'].map(value => <option key={value} value={value}>{t(LIBRARY_FORMAT_LABEL_KEYS[value])}</option>)}</select></label>
      <label className="grid gap-1 text-sm">{t('podcasts.podcastLibrary.profile')}<select aria-label={t('podcasts.podcastLibrary.profileFilter')} value={profile} onChange={event => setProfile(event.target.value)} className="h-9 rounded-md border bg-background px-2"><option value="all">{t('podcasts.podcastLibrary.allProfiles')}</option>{profiles.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <label className="grid gap-1 text-sm">{t('podcasts.podcastLibrary.productionStage')}<select aria-label={t('podcasts.podcastLibrary.productionStageFilter')} value={stage} onChange={event => setStage(event.target.value)} className="h-9 rounded-md border bg-background px-2"><option value="all">{t('podcasts.podcastLibrary.allStages')}</option>{stageOptions.map(value => <option key={value} value={value}>{LIBRARY_STAGE_LABEL_KEYS[value] ? t(LIBRARY_STAGE_LABEL_KEYS[value]) : value.replaceAll('_', ' ')}</option>)}</select></label>
      <label className="grid gap-1 text-sm">{t('podcasts.podcastLibrary.created')}<select aria-label={t('podcasts.podcastLibrary.createdDateFilter')} value={date} onChange={event => setDate(event.target.value as LibraryDateFilter)} className="h-9 rounded-md border bg-background px-2"><option value="all">{t('podcasts.podcastLibrary.anyDate')}</option><option value="seven_days">{t('podcasts.podcastLibrary.past7Days')}</option><option value="thirty_days">{t('podcasts.podcastLibrary.past30Days')}</option><option value="older">{t('podcasts.podcastLibrary.olderThan30Days')}</option></select></label>
      <label className="grid gap-1 text-sm">{t('podcasts.podcastLibrary.selectionAuthority')}<select aria-label={t('podcasts.podcastLibrary.selectionAuthorityFilter')} value={authority} onChange={event => setAuthority(event.target.value as LibraryAuthorityFilter)} className="h-9 rounded-md border bg-background px-2"><option value="all">{t('podcasts.podcastLibrary.allAuthority')}</option><option value="app_owned">{t('podcasts.podcastLibrary.appOwned')}</option><option value="external_read_only">{t('podcasts.podcastLibrary.externalReadOnly')}</option></select></label>
      {/* v0.8.130 — was "Evidence filters — Phase 3": the teaser stays, the internal roadmap label goes. */}
      <Button type="button" size="sm" variant="outline" disabled title={t('podcasts.podcastLibrary.evidenceFiltersUnavailable')}>{t('podcasts.podcastLibrary.evidenceFiltersComingSoon')}</Button>
    </div>
    {(Object.entries(groups) as Array<[LibraryGroup, PodcastEpisode[]]>).map(([title, items]) => items.length > 0 && <section key={title} aria-label={t(LIBRARY_GROUP_LABEL_KEYS[title])} className="space-y-3"><h2 className="text-lg font-semibold">{t(LIBRARY_GROUP_LABEL_KEYS[title])}</h2><div className="space-y-4">{items.map(episode => <div key={episode.id} className="space-y-2"><Button type="button" size="sm" variant="outline" aria-label={t('podcasts.podcastLibrary.openEpisodeLabFor', { name: episode.name })} onClick={() => setLabEpisodeId(episode.id)}>{t('podcasts.podcastLibrary.openEpisodeLab')}</Button><EpisodeCard episode={episode} onDelete={onDelete} onRetry={onRetry} retrying={retrying} /></div>)}</div></section>)}
    {labEpisode ? <EpisodeLab episode={labEpisode} onClose={() => setLabEpisodeId(null)} onRetry={onRetry} onCancel={onCancel} onCitationClick={onCitationClick} retrying={retrying} /> : null}
    {filtered.length === 0 && <p className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">{episodes.length === 0 ? t('podcasts.podcastLibrary.noEpisodes') : t('podcasts.podcastLibrary.noMatchingEpisodes')}</p>}
  </section>
}

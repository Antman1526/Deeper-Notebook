'use client'

import { useEffect, useState } from 'react'
import { ArrowRight, BookOpenCheck, CheckCircle2, Clock3, Cpu, Download, FileJson, FileQuestion, GraduationCap, Layers3, ListChecks, Loader2, Map as MapIcon, Mic2, Newspaper, Play, Presentation, RefreshCw, Search, SlidersHorizontal, Trash2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { CitationDrawer, citationEvidenceFromRecord, type CitationEvidence } from '@/components/onp/CitationDrawer'
import { CitationCoverageBadge } from '@/components/onp/CitationCoverageBadge'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { getSourceReadiness, SourceHealthPill } from '@/components/onp/SourceHealthPill'
import {
  CoursePackViewer,
  FlashcardDeck,
  parseFlashcards,
  parseQuizQuestions,
  QuizRunner,
  ResearchRunViewer,
} from '@/components/onp/StudyArtifactViewers'
import { isEvidenceStudioEnabled, isResearchRunsEnabled } from '@/lib/features'
import {
  useCreateStudioArtifact,
  useApproveStudioWorkflowRun,
  useCreateStudioWorkflowRun,
  useDeleteStudioArtifact,
  useStudioArtifactRevisions,
  useGenerateStudioArtifact,
  useStudioArtifacts,
  useStudioWorkflowRuns,
} from '@/lib/hooks/use-studio'
import { cn } from '@/lib/utils'
import type { StudioArtifact, StudioArtifactType, StudioWorkflowRun } from '@/lib/api/studio'
import type { SourceListResponse } from '@/lib/types/api'

const ICONS: Partial<Record<StudioArtifactType, typeof Newspaper>> = {
  report: Newspaper,
  study_guide: BookOpenCheck,
  course_pack: GraduationCap,
  training_guide: GraduationCap,
  briefing: Newspaper,
  faq: FileQuestion,
  timeline: ListChecks,
  quiz: FileQuestion,
  flashcards: ListChecks,
  mind_map: MapIcon,
  slide_deck: Presentation,
  infographic: Layers3,
  podcast_outline: Mic2,
  research_run: Search,
}

type QuickArtifactType =
  | 'report'
  | 'study_guide'
  | 'course_pack'
  | 'briefing'
  | 'faq'
  | 'timeline'
  | 'mind_map'
  | 'slide_deck'
  | 'infographic'
  | 'podcast_outline'
  | 'research_run'
  | 'flashcards'
  | 'quiz'

const QUICK_ARTIFACTS: Array<{
  type: QuickArtifactType
  title: string
  label: string
  Icon: typeof Newspaper
}> = [
  { type: 'report', title: 'Report', label: 'Report', Icon: Newspaper },
  { type: 'study_guide', title: 'Study guide', label: 'Study guide', Icon: BookOpenCheck },
  { type: 'course_pack', title: 'Course Pack', label: 'Course Pack', Icon: GraduationCap },
  { type: 'briefing', title: 'Briefing', label: 'Briefing', Icon: Newspaper },
  { type: 'faq', title: 'FAQ', label: 'FAQ', Icon: FileQuestion },
  { type: 'timeline', title: 'Timeline', label: 'Timeline', Icon: ListChecks },
  { type: 'mind_map', title: 'Mind map', label: 'Mind map', Icon: MapIcon },
  { type: 'slide_deck', title: 'Slide deck', label: 'Slide deck', Icon: Presentation },
  { type: 'infographic', title: 'Infographic', label: 'Infographic', Icon: Layers3 },
  { type: 'podcast_outline', title: 'Podcast outline', label: 'Podcast outline', Icon: Mic2 },
  { type: 'flashcards', title: 'Flashcards', label: 'Flashcards', Icon: ListChecks },
  { type: 'quiz', title: 'Quiz', label: 'Quiz', Icon: FileQuestion },
]

const RESEARCH_RUN_ARTIFACT = {
  type: 'research_run',
  title: 'Research run',
  label: 'Research run',
  Icon: Search,
} satisfies {
  type: QuickArtifactType
  title: string
  label: string
  Icon: typeof Newspaper
}

function artifactTypeLabel(type: StudioArtifactType): string {
  if (type === 'course_pack' || type === 'training_guide') return 'Course Pack'
  return type.replace(/_/g, ' ')
}

function statusClassName(status: StudioArtifact['status']): string {
  if (status === 'completed') return 'border-[var(--onp-success)] text-[var(--onp-success)]'
  if (status === 'failed' || status === 'cancelled') return 'border-destructive text-destructive'
  if (status === 'running') return 'border-[var(--onp-info)] text-[var(--onp-info)]'
  return 'border-[var(--onp-warning)] text-[var(--onp-warning)]'
}

function artifactMarkdown(artifact: StudioArtifact | null): string {
  const content = artifact?.output_payload?.content
  return typeof content === 'string' ? content : ''
}

function artifactFileName(artifact: StudioArtifact): string {
  const slug = artifact.title
    .trim()
    .replace(/[^A-Za-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `${slug || 'artifact'}.md`
}

function artifactJsonFileName(artifact: StudioArtifact): string {
  return artifactFileName(artifact).replace(/\.md$/, '.json')
}

function markdownHref(markdown: string): string {
  return `data:text/markdown;charset=utf-8,${encodeURIComponent(markdown)}`
}

function jsonHref(artifact: StudioArtifact): string {
  return `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(artifact, null, 2))}`
}

function artifactExportEntries(artifact: StudioArtifact | null): Array<[string, string]> {
  if (!artifact) return []
  const exportPaths = artifact.export_paths ?? {}
  const entries = Object.entries(exportPaths).filter((entry): entry is [string, string] => {
    return typeof entry[1] === 'string' && entry[1].trim().length > 0
  })
  const priority: Record<string, number> = {
    markdown: 0,
    md: 0,
    json: 1,
  }
  return entries.sort(([left], [right]) => {
    const leftPriority = priority[left.toLowerCase()] ?? 10
    const rightPriority = priority[right.toLowerCase()] ?? 10
    if (leftPriority !== rightPriority) return leftPriority - rightPriority
    return left.localeCompare(right)
  })
}

function exportLabel(format: string): string {
  if (format.toLowerCase() === 'json') return 'JSON'
  if (format.toLowerCase() === 'md') return 'Markdown'
  return format
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function sourceTitle(source: SourceListResponse): string {
  return source.title || source.asset?.file_path || source.asset?.url || source.id
}

function sourceSelectionLabel(selectedCount: number): string {
  if (selectedCount === 0) return 'All sources'
  return `${selectedCount} ${selectedCount === 1 ? 'source' : 'sources'} selected`
}

function sourceHref(sourceId: string): string {
  return `/sources/${encodeURIComponent(sourceId)}`
}

function regenerateArtifactLabel(status: StudioArtifact['status']): string {
  return status === 'failed' ? 'Retry' : 'Regenerate'
}

function artifactStats(artifacts: StudioArtifact[]) {
  return {
    completed: artifacts.filter((artifact) => artifact.status === 'completed').length,
    active: artifacts.filter((artifact) => artifact.status === 'pending' || artifact.status === 'running').length,
    citations: artifacts.reduce((total, artifact) => total + artifact.citations.length, 0),
  }
}

function workflowRunStatusLabel(status?: StudioWorkflowRun['status']): string {
  return (status ?? 'queued').replace(/_/g, ' ')
}

function workflowRunStatusClassName(status?: StudioWorkflowRun['status']): string {
  if (status === 'completed') return 'border-[var(--onp-success)] text-[var(--onp-success)]'
  if (status === 'failed' || status === 'cancelled') return 'border-destructive text-destructive'
  if (status === 'running') return 'border-[var(--onp-info)] text-[var(--onp-info)]'
  return 'border-[var(--onp-warning)] text-[var(--onp-warning)]'
}

function workflowStepClassName(status: string): string {
  if (status === 'completed') return 'border-[var(--onp-success)] bg-[var(--onp-success-soft)]'
  if (status === 'running') return 'border-[var(--onp-info)] bg-[var(--onp-info-soft)]'
  if (status === 'failed') return 'border-destructive bg-destructive/10'
  if (status === 'blocked') return 'border-muted bg-muted/50 text-muted-foreground'
  return 'border-[var(--onp-warning)] bg-[var(--onp-warning-soft)]'
}

function workflowRunTimestamp(run: StudioWorkflowRun): string {
  return run.updated || run.created || run.id
}

export function ArtifactRail({
  notebookId,
  sources = [],
  sourcesLoading = false,
}: {
  notebookId: string
  sources?: SourceListResponse[]
  sourcesLoading?: boolean
}) {
  const [selectedArtifact, setSelectedArtifact] = useState<StudioArtifact | null>(null)
  const [selectedCitation, setSelectedCitation] = useState<CitationEvidence | null>(null)
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([])
  const enabled = isEvidenceStudioEnabled()
  const researchRunsEnabled = isResearchRunsEnabled()
  const { data: artifacts = [], isLoading } = useStudioArtifacts(notebookId, {
    enabled,
  })
  const createArtifact = useCreateStudioArtifact(notebookId)
  const createWorkflowRun = useCreateStudioWorkflowRun(notebookId)
  const approveWorkflowRun = useApproveStudioWorkflowRun(notebookId)
  const generateArtifact = useGenerateStudioArtifact(notebookId)
  const deleteArtifact = useDeleteStudioArtifact(notebookId)
  const artifactIds = artifacts.map((artifact) => artifact.id)
  const { data: workflowRuns = [], isLoading: workflowRunsLoading } = useStudioWorkflowRuns(
    artifactIds,
    { enabled: enabled && artifactIds.length > 0 },
  )
  const { data: artifactRevisions = [], isLoading: revisionsLoading } = useStudioArtifactRevisions(
    selectedArtifact?.id ?? null,
    { enabled: enabled && Boolean(selectedArtifact) },
  )
  const isCreating = (
    createArtifact.isPending
    || createWorkflowRun.isPending
    || approveWorkflowRun.isPending
    || generateArtifact.isPending
  )
  const selectedMarkdown = artifactMarkdown(selectedArtifact)
  const selectedExportEntries = artifactExportEntries(selectedArtifact)
  const flashcardCount = selectedArtifact?.artifact_type === 'flashcards'
    ? parseFlashcards(selectedMarkdown).length
    : 0
  const quizQuestionCount = selectedArtifact?.artifact_type === 'quiz'
    ? parseQuizQuestions(selectedMarkdown).length
    : 0
  const sourceLabel = sourceSelectionLabel(selectedSourceIds.length)
  const scopedSources = selectedSourceIds.length === 0
    ? sources
    : sources.filter((source) => selectedSourceIds.includes(source.id))
  const blockedSources = scopedSources.filter((source) => getSourceReadiness(source).blocksGeneration)
  const generationBlocked = sourcesLoading || sources.length === 0 || blockedSources.length > 0
  const blockedSourceMessage = sourcesLoading
    ? 'Sources are still loading.'
    : sources.length === 0
      ? 'Add at least one ready source before generating artifacts.'
      : blockedSources.length === 1
        ? '1 source is not ready for artifact generation.'
        : `${blockedSources.length} sources are not ready for artifact generation.`
  const stats = artifactStats(artifacts)
  const artifactsById = new Map(artifacts.map((artifact) => [artifact.id, artifact]))
  const quickArtifacts = researchRunsEnabled
    ? [...QUICK_ARTIFACTS, RESEARCH_RUN_ARTIFACT]
    : QUICK_ARTIFACTS

  useEffect(() => {
    if (sources.length === 0 || selectedSourceIds.length === 0) return
    const sourceIds = new Set(sources.map((source) => source.id))
    const nextSelected = selectedSourceIds.filter((sourceId) => sourceIds.has(sourceId))
    if (nextSelected.length !== selectedSourceIds.length) {
      setSelectedSourceIds(nextSelected)
    }
  }, [sources, selectedSourceIds])

  function toggleSource(sourceId: string, checked: boolean) {
    setSelectedSourceIds((current) => {
      if (checked) {
        return current.includes(sourceId) ? current : [...current, sourceId]
      }
      return current.filter((id) => id !== sourceId)
    })
  }

  async function createAndQueue(type: QuickArtifactType, title: string) {
    if (generationBlocked) return
    const artifact = await createArtifact.mutateAsync({
      notebook_id: notebookId,
      artifact_type: type,
      title,
      source_ids: selectedSourceIds,
    })
    await createWorkflowRun.mutateAsync({
      artifactId: artifact.id,
      payload: {
        title: `Generate ${title}`,
        source_ids: selectedSourceIds,
        approval_required: true,
      },
    })
  }

  async function approveAndGenerate(run: StudioWorkflowRun) {
    await approveWorkflowRun.mutateAsync(run.id)
    await generateArtifact.mutateAsync(run.artifact_id)
  }

  async function deleteSelectedArtifact(artifact: StudioArtifact) {
    if (!window.confirm(`Delete "${artifact.title}"?`)) return
    await deleteArtifact.mutateAsync(artifact.id)
    setSelectedArtifact(null)
    setSelectedCitation(null)
  }

  if (!enabled) return null

  return (
    <section
      aria-label="Evidence Studio artifacts"
      className="mb-5 overflow-hidden rounded-lg border border-[var(--onp-border-strong)] bg-card shadow-[var(--onp-elevation-md)]"
    >
      <div className="flex flex-col gap-3 border-b bg-[var(--onp-surface-raised)] px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 flex-none items-center justify-center rounded-md border border-[var(--onp-border-strong)] bg-background text-primary shadow-[var(--onp-elevation-low)]">
            <Layers3 className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold">Evidence Studio</div>
            <div className="text-xs text-muted-foreground">
              {isLoading
                ? 'Artifacts are loading'
                : artifacts.length === 0
                  ? 'Awaiting first artifact'
                  : `${artifacts.length} ${artifacts.length === 1 ? 'artifact' : 'artifacts'}`}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant="outline" className="bg-background/70 text-[0.72rem]">
            {stats.completed} completed
          </Badge>
          <Badge variant="outline" className="bg-background/70 text-[0.72rem]">
            {stats.active} in progress
          </Badge>
          <Badge variant="outline" className="bg-background/70 text-[0.72rem]">
            {stats.citations} {stats.citations === 1 ? 'citation' : 'citations'}
          </Badge>
        </div>
      </div>

      <div className="grid gap-3 px-4 py-3">
        <div className="flex min-w-0 gap-2 overflow-x-auto pb-1">
          {isLoading && (
            <div className="flex min-h-12 items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Loading artifacts
            </div>
          )}

          {!isLoading && artifacts.length === 0 && (
            <div className="flex min-h-12 items-center rounded-md border border-dashed px-3 text-sm text-muted-foreground">
              No saved research outputs in this notebook.
            </div>
          )}

          {!isLoading && artifacts.map((artifact) => {
            const Icon = ICONS[artifact.artifact_type] ?? Newspaper
            return (
              <button
                type="button"
                key={artifact.id}
                aria-label={`Open ${artifact.title}`}
                onClick={() => {
                  setSelectedArtifact(artifact)
                  setSelectedCitation(null)
                }}
                className="flex min-h-14 min-w-56 max-w-72 flex-none items-center gap-2 rounded-md border bg-background px-3 py-2 text-left transition-colors hover:border-[var(--onp-border-strong)] hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Icon className="h-4 w-4 flex-none text-muted-foreground" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{artifact.title}</div>
                  <div className="mt-1 flex min-w-0 items-center gap-1.5">
                    <span className="truncate text-xs text-muted-foreground">
                      {artifactTypeLabel(artifact.artifact_type)}
                    </span>
                    <CitationCoverageBadge citationCount={artifact.citations.length} />
                  </div>
                </div>
                <Badge
                  variant="outline"
                  className={cn('flex-none text-[0.68rem]', statusClassName(artifact.status))}
                >
                  {artifact.status}
                </Badge>
              </button>
            )
          })}
        </div>

        <div className="rounded-md border bg-background/70 p-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-sm font-semibold">App Mode templates</div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <span>Source readiness</span>
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
                <span>Artifact generation</span>
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
                <span>Evidence export</span>
              </div>
            </div>
            <div className="text-xs text-muted-foreground">
              Pick sources once, then run a reusable grounded workflow.
            </div>
          </div>
        </div>

        {(workflowRunsLoading || workflowRuns.length > 0) && (
          <div className="rounded-md border bg-background/70 p-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <Clock3 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                <div className="text-sm font-semibold">Workflow runs</div>
              </div>
              <Badge variant="outline" className="w-fit text-[0.68rem]">
                {workflowRuns.length} {workflowRuns.length === 1 ? 'run' : 'runs'}
              </Badge>
            </div>

            {workflowRunsLoading ? (
              <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Loading run history
              </div>
            ) : (
              <div className="mt-3 grid gap-2">
                {workflowRuns.slice(0, 5).map((run) => {
                  const artifact = artifactsById.get(run.artifact_id)
                  const canApprove = run.status === 'awaiting_approval' && Boolean(artifact)
                  return (
                    <div
                      key={run.id}
                      className="rounded-md border bg-card px-3 py-2 shadow-[var(--onp-elevation-low)]"
                    >
                      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="truncate text-sm font-medium">{run.title}</div>
                            <Badge
                              variant="outline"
                              className={cn('text-[0.68rem]', workflowRunStatusClassName(run.status))}
                            >
                              {workflowRunStatusLabel(run.status)}
                            </Badge>
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {artifact?.title ?? run.artifact_id} - {workflowRunTimestamp(run)}
                          </div>
                        </div>

                        {canApprove && (
                          <Button
                            type="button"
                            size="sm"
                            disabled={isCreating}
                            aria-label={`Approve ${run.title}`}
                            onClick={() => void approveAndGenerate(run)}
                          >
                            {approveWorkflowRun.isPending || generateArtifact.isPending ? (
                              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                            ) : (
                              <Play className="h-4 w-4" aria-hidden="true" />
                            )}
                            Approve
                          </Button>
                        )}
                      </div>

                      {run.steps.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {run.steps.map((step) => (
                            <span
                              key={`${run.id}-${step.id}`}
                              className={cn(
                                'inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[0.68rem]',
                                workflowStepClassName(step.status),
                              )}
                            >
                              {step.status === 'completed' ? (
                                <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                              ) : step.status === 'running' ? (
                                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                              ) : (
                                <Clock3 className="h-3 w-3" aria-hidden="true" />
                              )}
                              {step.label}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        <div className="flex max-w-full flex-wrap gap-2">
          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                aria-label={`Artifact sources: ${sourceLabel}`}
                disabled={sourcesLoading || sources.length === 0}
              >
                <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
                {sourceLabel}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-80 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium">Artifact sources</div>
                  <div className="text-xs text-muted-foreground">
                    Empty selection uses every notebook source.
                  </div>
                </div>
                {selectedSourceIds.length > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedSourceIds([])}
                  >
                    Use all
                  </Button>
                )}
              </div>

              <ScrollArea className="mt-3 max-h-64 pr-2">
                <div className="space-y-2">
                  {sources.map((source) => {
                    const title = sourceTitle(source)
                    const checkboxId = `artifact-source-${source.id.replace(/[^A-Za-z0-9_-]/g, '-')}`
                    return (
                      <div
                        key={source.id}
                        className="flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-accent"
                      >
                        <Checkbox
                          id={checkboxId}
                          aria-label={title}
                          checked={selectedSourceIds.includes(source.id)}
                          onCheckedChange={(checked) => toggleSource(source.id, checked === true)}
                        />
                        <label
                          htmlFor={checkboxId}
                          className="min-w-0 flex-1 cursor-pointer text-sm leading-5"
                        >
                          <span className="block truncate">{title}</span>
                          <span className="mt-1 block">
                            <SourceHealthPill source={source} />
                          </span>
                        </label>
                      </div>
                    )
                  })}
                </div>
              </ScrollArea>
            </PopoverContent>
          </Popover>

          {quickArtifacts.map(({ type, title, label, Icon }) => (
            <Button
              key={type}
              variant="outline"
              size="sm"
              disabled={isCreating || generationBlocked}
              onClick={() => void createAndQueue(type, title)}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
            </Button>
          ))}
        </div>
      </div>

      {generationBlocked && (
        <div className="mt-2 rounded-md border border-[var(--onp-warning)] bg-[var(--onp-warning-soft)] px-3 py-2 text-xs text-muted-foreground">
          {blockedSourceMessage}
        </div>
      )}

      <Dialog
        open={Boolean(selectedArtifact)}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedArtifact(null)
            setSelectedCitation(null)
          }
        }}
      >
        <DialogContent className="max-h-[85vh] max-w-4xl bg-card text-card-foreground shadow-2xl">
          {selectedArtifact && (
            <>
              <DialogHeader>
                <DialogTitle>{selectedArtifact.title}</DialogTitle>
              </DialogHeader>

              <div className="grid min-h-0 gap-4 lg:grid-cols-[minmax(0,1fr)_15rem]">
                <ScrollArea className="max-h-[55vh] rounded-md border bg-background p-4">
                  {selectedMarkdown && selectedArtifact.artifact_type === 'flashcards' && flashcardCount > 0 ? (
                    <FlashcardDeck markdown={selectedMarkdown} />
                  ) : selectedMarkdown && selectedArtifact.artifact_type === 'quiz' && quizQuestionCount > 0 ? (
                    <QuizRunner markdown={selectedMarkdown} />
                  ) : selectedMarkdown && selectedArtifact.artifact_type === 'research_run' ? (
                    <ResearchRunViewer
                      markdown={selectedMarkdown}
                      stages={selectedArtifact.output_payload.research_stages}
                    />
                  ) : selectedMarkdown && (
                    selectedArtifact.artifact_type === 'course_pack'
                    || selectedArtifact.artifact_type === 'training_guide'
                  ) ? (
                    <CoursePackViewer markdown={selectedMarkdown} />
                  ) : selectedMarkdown ? (
                    <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none break-words prose-headings:font-semibold prose-p:leading-7">
                      <ReactMarkdown>{selectedMarkdown}</ReactMarkdown>
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground">
                      This artifact does not have markdown output yet.
                    </div>
                  )}
                </ScrollArea>

                <aside className="rounded-md border bg-muted/30 p-3">
                  {(selectedArtifact.model_id || selectedArtifact.provider) && (
                    <div className="mb-4 rounded-md border bg-background px-2 py-2">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <Cpu className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                        Model
                      </div>
                      {selectedArtifact.model_id && (
                        <div className="mt-1 truncate font-mono text-xs text-muted-foreground">
                          {selectedArtifact.model_id}
                        </div>
                      )}
                      {selectedArtifact.provider && (
                        <Badge variant="outline" className="mt-2 text-[0.68rem]">
                          {selectedArtifact.provider}
                        </Badge>
                      )}
                    </div>
                  )}
                  {selectedExportEntries.length > 0 && (
                    <div className="mb-4 rounded-md border bg-background px-2 py-2">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <Download className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                        Saved exports
                      </div>
                      <div className="mt-2 space-y-2">
                        {selectedExportEntries.map(([format, path]) => (
                          <div key={`${format}-${path}`} className="rounded-md border bg-muted/30 px-2 py-1.5">
                            <div className="text-[0.68rem] font-medium uppercase tracking-normal text-muted-foreground">
                              {exportLabel(format)}
                            </div>
                            <div
                              title={path}
                              className="mt-1 break-all font-mono text-[0.68rem] leading-4 text-muted-foreground"
                            >
                              {path}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium">Citations</div>
                    <CitationCoverageBadge citationCount={selectedArtifact.citations.length} />
                  </div>
                  {selectedArtifact.citations.length > 0 ? (
                    <ul className="mt-3 space-y-2 text-sm">
                      {selectedArtifact.citations.map((citation, index) => {
                        const hasSourceId = typeof citation.source_id === 'string'
                        const sourceId = hasSourceId
                          ? (citation.source_id as string)
                          : `source-${index + 1}`
                        const title =
                          typeof citation.title === 'string'
                            ? citation.title
                            : sourceId
                        const preview =
                          typeof citation.preview === 'string'
                            ? citation.preview
                            : ''
                        return (
                          <li key={`${sourceId}-${index}`} className="rounded-md bg-background px-2 py-1.5">
                            <div className="flex items-start justify-between gap-2">
                              {hasSourceId ? (
                                <a
                                  href={sourceHref(sourceId)}
                                  className="min-w-0 truncate font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                >
                                  {title}
                                </a>
                              ) : (
                                <div className="min-w-0 truncate font-medium">{title}</div>
                              )}
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                aria-label={`Inspect evidence for ${title}`}
                                className="h-7 w-7 flex-none p-0"
                                onClick={() => {
                                  setSelectedCitation(
                                    citationEvidenceFromRecord(citation, sourceId),
                                  )
                                }}
                              >
                                <Search className="h-3.5 w-3.5" aria-hidden="true" />
                              </Button>
                            </div>
                            <div className="truncate text-xs text-muted-foreground">{sourceId}</div>
                            {preview && (
                              <blockquote className="mt-2 line-clamp-4 border-l-2 border-[var(--onp-accent-strong)] pl-2 text-xs leading-5 text-muted-foreground">
                                {preview}
                              </blockquote>
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  ) : (
                    <div className="mt-3 text-sm text-muted-foreground">
                      No citations stored yet.
                    </div>
                  )}

                  <CitationDrawer
                    evidence={selectedCitation}
                    onClose={() => setSelectedCitation(null)}
                  />

                  <div className="mt-4 border-t pt-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-medium">Revision history</div>
                      {artifactRevisions.length > 0 && (
                        <Badge variant="outline" className="text-[0.68rem]">
                          {artifactRevisions.length} {artifactRevisions.length === 1 ? 'revision' : 'revisions'}
                        </Badge>
                      )}
                    </div>
                    {revisionsLoading ? (
                      <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                        Loading revisions
                      </div>
                    ) : artifactRevisions.length > 0 ? (
                      <ul className="mt-3 space-y-2">
                        {artifactRevisions.map((revision) => (
                          <li key={revision.id}>
                            <button
                              type="button"
                              aria-label={`Open ${revision.title}`}
                              onClick={() => setSelectedArtifact(revision)}
                              className="w-full rounded-md bg-background px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              <span className="block truncate font-medium">{revision.title}</span>
                              <span className="block truncate text-xs text-muted-foreground">
                                {revision.updated || revision.created || revision.id}
                              </span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="mt-3 text-sm text-muted-foreground">
                        No revisions stored yet.
                      </div>
                    )}
                  </div>
                </aside>
              </div>

              <DialogFooter className="gap-2 sm:gap-2">
                <Button
                  type="button"
                  variant="destructive"
                  disabled={deleteArtifact.isPending}
                  onClick={() => void deleteSelectedArtifact(selectedArtifact)}
                >
                  {deleteArtifact.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  )}
                  Delete
                </Button>
                <Button
                  type="button"
                  disabled={generateArtifact.isPending || selectedArtifact.status === 'running'}
                  onClick={() => void generateArtifact.mutateAsync(selectedArtifact.id)}
                >
                  {generateArtifact.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  )}
                  {regenerateArtifactLabel(selectedArtifact.status)}
                </Button>
                <Button asChild variant="outline">
                  <a
                    href={markdownHref(selectedMarkdown)}
                    download={artifactFileName(selectedArtifact)}
                    aria-disabled={!selectedMarkdown}
                    tabIndex={selectedMarkdown ? undefined : -1}
                    className={cn(!selectedMarkdown && 'pointer-events-none opacity-50')}
                  >
                    <Download className="h-4 w-4" aria-hidden="true" />
                    Download Markdown
                  </a>
                </Button>
                <Button asChild variant="outline">
                  <a
                    href={jsonHref(selectedArtifact)}
                    download={artifactJsonFileName(selectedArtifact)}
                  >
                    <FileJson className="h-4 w-4" aria-hidden="true" />
                    Download JSON
                  </a>
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}

/**
 * ONP v0.7.0 — Studio page.
 *
 * Single-page workflow: drag-and-drop files → pick mode → click Generate →
 * router pushes to /notebooks/{id} on success.
 *
 * Design choices:
 *  - Inline state, no Zustand store. The workflow is one-shot; no need
 *    for cross-component sharing.
 *  - Drag-and-drop OR file-picker — both go through the same handleFiles
 *    helper to validate + dedupe.
 *  - Per-file validation matches the backend's _ALLOWED_EXTENSIONS list.
 *    We do this client-side too so the user gets immediate feedback
 *    rather than a backend 400 after the upload completes.
 *  - Podcast mode shows the EpisodeProfile + SpeakerProfile dropdowns,
 *    populated from existing /api/episode-profiles + /api/speaker-profiles.
 *  - On success: small toast + router.push(/notebooks/{id}). The user
 *    can then chat-with-sources or wait for podcast generation to finish.
 *  - Warnings from the backend (non-fatal extraction issues) surface as
 *    a yellow banner before navigating.
 */
'use client'

import { useState, useCallback, useRef, DragEvent, ChangeEvent, KeyboardEvent } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Upload, FileText, X, Loader2, AlertCircle, BookOpen, Mic, ArrowLeft } from 'lucide-react'

import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/lib/hooks/use-toast'
import { useStudioGenerate } from '@/lib/hooks/use-studio'
import { StudioMode } from '@/lib/api/studio'
import apiClient from '@/lib/api/client'
// v0.7.1 — use existing QUERY_KEYS so Studio's profile fetches share
// cache with use-podcasts.ts (and pick up invalidations from profile
// mutations). Previously this file declared its own raw keys, causing
// duplicate network requests + stale data.
import { QUERY_KEYS } from '@/lib/api/query-client'

// Must match api/routers/studio.py:_ALLOWED_EXTENSIONS
const ALLOWED_EXTS = new Set([
  '.pdf', '.docx', '.txt', '.md', '.markdown',
  '.pptx', '.html', '.htm',
])
const MAX_FILE_MB = 50

interface ProfileSummary {
  name: string
  description?: string | null
}

function fileExt(name: string): string {
  const i = name.lastIndexOf('.')
  return i < 0 ? '' : name.slice(i).toLowerCase()
}

function isAllowed(file: File): { ok: boolean; reason?: string } {
  const ext = fileExt(file.name)
  if (!ALLOWED_EXTS.has(ext)) {
    return { ok: false, reason: `unsupported type ${ext || '(no extension)'}` }
  }
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    return { ok: false, reason: `file is ${Math.round(file.size / 1024 / 1024)} MB; cap is ${MAX_FILE_MB} MB` }
  }
  return { ok: true }
}

export default function StudioPage() {
  const router = useRouter()
  const { toast } = useToast()
  const mutation = useStudioGenerate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [files, setFiles] = useState<File[]>([])
  const [mode, setMode] = useState<StudioMode>('notebook')
  const [title, setTitle] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const [episodeProfile, setEpisodeProfile] = useState('')
  const [speakerProfile, setSpeakerProfile] = useState('')

  // Fetch episode + speaker profiles for the podcast mode dropdowns.
  // Cheap — both queries return a small list and TanStack caches them.
  const { data: episodeProfiles = [] } = useQuery<ProfileSummary[]>({
    queryKey: QUERY_KEYS.episodeProfiles,
    queryFn: async () => (await apiClient.get('/episode-profiles')).data,
    enabled: mode === 'podcast',
  })
  const { data: speakerProfiles = [] } = useQuery<ProfileSummary[]>({
    queryKey: QUERY_KEYS.speakerProfiles,
    queryFn: async () => (await apiClient.get('/speaker-profiles')).data,
    enabled: mode === 'podcast',
  })

  // ----- File handling -----
  const addFiles = useCallback((incoming: FileList | File[]) => {
    const rejected: { name: string; reason: string }[] = []
    const accepted: File[] = []
    for (const f of Array.from(incoming)) {
      const { ok, reason } = isAllowed(f)
      if (!ok) {
        rejected.push({ name: f.name, reason: reason || 'rejected' })
        continue
      }
      // Dedupe by (name, size) — close enough without computing a hash
      if (files.some((existing) => existing.name === f.name && existing.size === f.size)) {
        continue
      }
      accepted.push(f)
    }
    if (accepted.length > 0) setFiles((prev) => [...prev, ...accepted])
    if (rejected.length > 0) {
      toast({
        title: `${rejected.length} file${rejected.length === 1 ? '' : 's'} rejected`,
        description: rejected.map((r) => `${r.name}: ${r.reason}`).join('; '),
        variant: 'destructive',
      })
    }
  }, [files, toast])

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  // ----- DnD handlers -----
  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }
  const onDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
  }
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files)
  }
  const onFileInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) addFiles(e.target.files)
    // Reset input so re-selecting the same file fires onchange again
    if (e.target) e.target.value = ''
  }

  // v0.7.1 — keyboard activation for the drop zone. The element advertises
  // itself as role="button" + tabIndex={0}, so screen readers and
  // keyboard-only users expect Enter/Space to activate. Without this
  // handler, focus lands on the zone but nothing happens — WCAG 2.1.1
  // (keyboard) violation. Standard fix: handle Enter + Space, preventDefault
  // on Space to stop page scroll.
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      fileInputRef.current?.click()
    }
  }

  // ----- Submit -----
  const canSubmit = files.length > 0 && !mutation.isPending && (
    mode === 'notebook' || (episodeProfile && speakerProfile)
  )

  const onGenerate = async () => {
    try {
      const result = await mutation.mutateAsync({
        files,
        mode,
        title: title.trim() || undefined,
        episode_profile_name: mode === 'podcast' ? episodeProfile : undefined,
        speaker_profile_name: mode === 'podcast' ? speakerProfile : undefined,
      })
      // Warnings, if any
      if (result.warnings.length > 0) {
        toast({
          title: 'Generated with warnings',
          description: result.warnings.join('; '),
        })
      } else {
        toast({
          title: mode === 'notebook' ? 'Notebook generated' : 'Podcast generation started',
          description:
            mode === 'notebook'
              ? `Navigating to the new notebook…`
              : `Job ${result.job_id}. Audio will appear in /podcasts when done.`,
        })
      }
      router.push(`/notebooks/${encodeURIComponent(result.notebook_id)}`)
    } catch (e) {
      const msg = (e as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail
        || (e as Error)?.message
        || 'Generation failed'
      toast({
        title: 'Studio generation failed',
        description: msg,
        variant: 'destructive',
      })
    }
  }

  // ----- Render -----
  // v0.7.23 — wrap in AppShell so the persistent left sidebar is visible
  // (matches every other dashboard page). Studio previously rendered a
  // bare <div> with no nav — users had no way back to the main page short
  // of the browser back button. Also adds an explicit "Back to Notebooks"
  // header link as a one-click escape hatch independent of the sidebar.
  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="container mx-auto p-6 max-w-3xl">
          <div className="mb-4">
            <Link href="/notebooks">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Notebooks
              </Button>
            </Link>
          </div>
          {/* v0.7.164 — H1 hierarchy sweep. Was `text-2xl font-bold`
              with `mb-1` between title and description; now matches
              the v0.7.153 dashboard standard
              (`text-3xl font-semibold tracking-tight`) with a
              `space-y-2` stack for proper breathing. Subtitle
              bumped from `text-sm` to default body size — the
              Studio is a flagship feature; the explainer copy
              shouldn't read as a footnote. */}
          <header className="mb-6 space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight">Studio</h1>
            <p className="text-muted-foreground max-w-3xl">
              Upload one or more documents (PDF, DOCX, MD, TXT, HTML, PPTX) and
              generate either a structured study notebook or a two-host podcast
              episode, grounded in your sources.
            </p>
          </header>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>1. Upload documents</CardTitle>
          <CardDescription>
            Drag-and-drop, or click to browse. Up to {MAX_FILE_MB} MB per file.
            Multiple files are combined into a single context.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={onKeyDown}
            className={`
              border-2 border-dashed rounded-lg p-8 text-center cursor-pointer
              transition-colors
              focus-visible:outline-none focus-visible:ring-2
              focus-visible:ring-ring focus-visible:ring-offset-2
              ${isDragging
                ? 'border-primary bg-primary/5'
                : 'border-muted-foreground/30 hover:border-muted-foreground/60'}
            `}
            role="button"
            tabIndex={0}
            aria-label="Upload files"
          >
            <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
            <p className="text-sm">
              Drop files here or <span className="text-primary underline">browse</span>
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {Array.from(ALLOWED_EXTS).sort().join(', ')}
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={Array.from(ALLOWED_EXTS).join(',')}
              onChange={onFileInputChange}
              className="hidden"
            />
          </div>

          {files.length > 0 && (
            <ul className="mt-4 space-y-1">
              {files.map((f, i) => (
                <li
                  key={`${f.name}-${i}`}
                  className="flex items-center gap-2 px-3 py-1.5 rounded bg-muted/50 text-sm"
                >
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate">{f.name}</span>
                  <span className="text-xs text-muted-foreground shrink-0">
                    {(f.size / 1024).toFixed(0)} KB
                  </span>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); removeFile(i) }}
                    className="p-0.5 hover:bg-muted rounded"
                    aria-label={`Remove ${f.name}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>2. Pick output mode</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setMode('notebook')}
              className={`
                border rounded-lg p-4 text-left transition-colors
                ${mode === 'notebook'
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/20 hover:border-muted-foreground/40'}
              `}
            >
              <BookOpen className="h-5 w-5 mb-2 text-primary" />
              <div className="font-medium">Study notebook</div>
              <div className="text-xs text-muted-foreground mt-1">
                Structured markdown: overview, sections, definitions, Q&amp;A.
                Saved as an AI-authored note attached to the new notebook.
              </div>
            </button>

            <button
              type="button"
              onClick={() => setMode('podcast')}
              className={`
                border rounded-lg p-4 text-left transition-colors
                ${mode === 'podcast'
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/20 hover:border-muted-foreground/40'}
              `}
            >
              <Mic className="h-5 w-5 mb-2 text-primary" />
              <div className="font-medium">Podcast episode</div>
              <div className="text-xs text-muted-foreground mt-1">
                Two-host conversational episode rendered to audio via the
                configured TTS profile. Status visible in /podcasts.
              </div>
            </button>
          </div>

          {mode === 'podcast' && (
            <div className="grid grid-cols-2 gap-3 pt-2">
              <div className="space-y-1.5">
                <Label htmlFor="ep-profile" className="text-xs">Episode profile</Label>
                <Select value={episodeProfile} onValueChange={setEpisodeProfile}>
                  <SelectTrigger id="ep-profile" className="h-9 text-sm">
                    <SelectValue placeholder="Pick a profile…" />
                  </SelectTrigger>
                  <SelectContent>
                    {episodeProfiles.map((p) => (
                      <SelectItem key={p.name} value={p.name}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sp-profile" className="text-xs">Speaker profile</Label>
                <Select value={speakerProfile} onValueChange={setSpeakerProfile}>
                  <SelectTrigger id="sp-profile" className="h-9 text-sm">
                    <SelectValue placeholder="Pick speakers…" />
                  </SelectTrigger>
                  <SelectContent>
                    {speakerProfiles.map((p) => (
                      <SelectItem key={p.name} value={p.name}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          <div className="space-y-1.5 pt-2">
            <Label htmlFor="title" className="text-xs">
              Title (optional — auto-generated from first filename if blank)
            </Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. 'Quantum Computing Primer'"
              className="h-9 text-sm"
            />
          </div>
        </CardContent>
      </Card>

      {mutation.isError && (
        <div className="mb-4 p-3 rounded border border-destructive/50 bg-destructive/10 flex items-start gap-2">
          <AlertCircle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
          <div className="text-sm text-destructive">
            {/* v0.7.1 — extract the backend's `detail` field from axios's
                response chain when present. Otherwise we'd show generic
                "Request failed with status code 400" instead of the
                actual reason from the API (e.g. "No usable text could
                be extracted…"). Matches the toast behavior in
                onGenerate's catch branch. */}
            {(mutation.error as { response?: { data?: { detail?: string } }; message?: string })
              ?.response?.data?.detail
              || (mutation.error as Error)?.message
              || 'Generation failed.'}
          </div>
        </div>
      )}

          <div className="flex justify-end">
            <Button onClick={onGenerate} disabled={!canSubmit} size="lg">
              {mutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  {mode === 'notebook' ? 'Generating study notebook…' : 'Submitting podcast job…'}
                </>
              ) : (
                <>Generate {mode === 'notebook' ? 'Notebook' : 'Podcast'}</>
              )}
            </Button>
          </div>
        </div>
      </div>
    </AppShell>
  )
}

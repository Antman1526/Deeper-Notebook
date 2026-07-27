/**
 * v0.7.29 — Dashboard Command Center landing page.
 *
 * Replaces the previous `redirect('/notebooks')` stub. The dashboard
 * is now a glanceable home that surfaces:
 *   - Quick actions for the four main verbs (Studio / New Notebook /
 *     Podcast / Ask)
 *   - Recent notebooks (last 5 by updated time) with one-click open
 *   - System status from /readyz (DB, migrations) — the v0.7.15
 *     endpoint, surfaced visually instead of as a hidden curl probe
 *   - Stat strip: notebook count, source count (best-effort)
 *
 * Design philosophy:
 *   - Dense information layout — not consumer-app gloss; researcher
 *     workstation chrome.
 *   - Uses the v0.7.27 semantic tokens (--success / --warning /
 *     --info) so colors track the active theme correctly.
 *   - Subtle hover lifts via shadow, no scale-transform tricks
 *     (the v0.7.25 lesson).
 *   - Loading states are skeletons, not spinners — feels faster.
 */
'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { motion, useReducedMotion } from 'framer-motion'
import {
  ArrowRight,
  Book,
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  Database,
  FileText,
  Mic,
  Search,
  Sparkles,
} from 'lucide-react'

import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { useSystemStatus } from '@/lib/hooks/use-system-status'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'

// Helpers -----------------------------------------------------------

function relativeTime(iso?: string): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const diff = Date.now() - then
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} min ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} hr ago`
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} d ago`
  return new Date(iso).toLocaleDateString()
}

interface StatusRowProps {
  label: string
  state: 'ok' | 'warn' | 'down' | 'unknown'
  detail?: string | null
}

function StatusRow({ label, state, detail }: StatusRowProps) {
  const icon =
    state === 'ok' ? (
      <CheckCircle2 className="h-4 w-4 text-success" />
    ) : state === 'warn' ? (
      <CircleAlert className="h-4 w-4 text-warning" />
    ) : state === 'down' ? (
      <CircleAlert className="h-4 w-4 text-destructive" />
    ) : (
      <CircleDashed className="h-4 w-4 text-muted-foreground" />
    )
  return (
    <div className="flex items-center justify-between py-2 text-sm">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-foreground">{label}</span>
      </div>
      <span
        className={
          state === 'ok'
            ? 'text-xs text-success'
            : state === 'warn'
              ? 'text-xs text-warning'
              : state === 'down'
                ? 'text-xs text-destructive'
                : 'text-xs text-muted-foreground'
        }
      >
        {state === 'ok' ? 'ready' : detail ?? state}
      </span>
    </div>
  )
}

// Page --------------------------------------------------------------

export default function DashboardPage() {
  const router = useRouter()
  const { data: notebooks, isLoading: notebooksLoading } = useNotebooks(false)
  const { data: status } = useSystemStatus()
  const { openNotebookDialog, openPodcastDialog } = useCreateDialogs()

  const recentNotebooks = (notebooks ?? []).slice(0, 5)
  const totalNotebooks = notebooks?.length ?? 0

  // v0.8.70 — gentle staggered entrance (reduced-motion aware).
  const reduce = useReducedMotion() ?? false
  const stagger = {
    hidden: {},
    show: {
      transition: {
        staggerChildren: reduce ? 0 : 0.08,
        delayChildren: reduce ? 0 : 0.04,
      },
    },
  }
  const item = {
    hidden: { opacity: 0, y: reduce ? 0 : 14 },
    show: {
      opacity: 1,
      y: 0,
      transition: { duration: reduce ? 0.2 : 0.5, ease: [0.22, 1, 0.36, 1] as const },
    },
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <motion.div
          className="container mx-auto p-6 max-w-6xl space-y-6"
          variants={stagger}
          initial="hidden"
          animate="show"
        >
          {/* Aurora hero header */}
          <motion.header
            variants={item}
            className="dn-aurora-bg relative overflow-hidden rounded-2xl border border-[var(--dn-glass-border)] px-6 py-7"
          >
            <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Deeper Notebook
            </h1>
            <p className="mt-1.5 text-sm text-muted-foreground">
              Think further with every source
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {totalNotebooks} notebook
              {totalNotebooks === 1 ? '' : 's'}
            </p>
          </motion.header>

          {/* Two-column row: Quick Actions + System Status */}
          <motion.div variants={item} className="grid gap-4 md:grid-cols-3">
            <Card className="md:col-span-2">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Quick actions</CardTitle>
                <CardDescription>Start something new</CardDescription>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Link href="/studio" className="block">
                  <Card className="dn-glass h-full border-primary/30 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--dn-glow-accent)] focus-within:ring-2 focus-within:ring-ring">
                    <CardContent className="flex flex-col items-start gap-2 p-4">
                      <Sparkles className="h-5 w-5 text-primary" />
                      <div>
                        <div className="text-sm font-semibold">Studio</div>
                        <div className="text-xs text-muted-foreground">
                          Drop files → notebook or podcast
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
                <button
                  type="button"
                  onClick={() => openNotebookDialog()}
                  className="text-left"
                >
                  <Card className="dn-glass h-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-within:ring-2 focus-within:ring-ring">
                    <CardContent className="flex flex-col items-start gap-2 p-4">
                      <Book className="h-5 w-5" />
                      <div>
                        <div className="text-sm font-semibold">New notebook</div>
                        <div className="text-xs text-muted-foreground">
                          Empty canvas
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </button>
                <button
                  type="button"
                  onClick={() => openPodcastDialog()}
                  className="text-left"
                >
                  <Card className="dn-glass h-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-within:ring-2 focus-within:ring-ring">
                    <CardContent className="flex flex-col items-start gap-2 p-4">
                      <Mic className="h-5 w-5" />
                      <div>
                        <div className="text-sm font-semibold">Podcast</div>
                        <div className="text-xs text-muted-foreground">
                          Generate from sources
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </button>
                <Link href="/search" className="block">
                  <Card className="dn-glass h-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-within:ring-2 focus-within:ring-ring">
                    <CardContent className="flex flex-col items-start gap-2 p-4">
                      <Search className="h-5 w-5" />
                      <div>
                        <div className="text-sm font-semibold">Ask</div>
                        <div className="text-xs text-muted-foreground">
                          Search + synthesize
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              </CardContent>
            </Card>

            {/* System status */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">System status</CardTitle>
                <CardDescription>
                  Updated every 30 s from /readyz
                </CardDescription>
              </CardHeader>
              <CardContent className="divide-y divide-border">
                <StatusRow
                  label="API"
                  state={status ? 'ok' : 'unknown'}
                />
                <StatusRow
                  label="Database"
                  state={
                    status?.checks.database === 'online'
                      ? 'ok'
                      : status?.checks.database === 'offline'
                        ? 'down'
                        : 'unknown'
                  }
                  detail={status?.checks.database_error ?? null}
                />
                <StatusRow
                  label="Migrations"
                  state={
                    status?.checks.migrations_applied
                      ? 'ok'
                      : status?.checks.migrations_pending
                        ? 'warn'
                        : status?.checks.migrations_error
                          ? 'down'
                          : 'unknown'
                  }
                  detail={
                    status?.checks.migrations_pending
                      ? 'pending'
                      : status?.checks.migrations_error
                  }
                />
              </CardContent>
            </Card>
          </motion.div>

          {/* Recent notebooks */}
          <motion.div variants={item}>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base">Recent notebooks</CardTitle>
                <CardDescription>Pick up where you left off</CardDescription>
              </div>
              <Button variant="ghost" size="sm" asChild>
                <Link href="/notebooks">
                  All notebooks
                  <ArrowRight className="ml-1 h-3.5 w-3.5" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent className="space-y-1">
              {notebooksLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-md px-3 py-2"
                  >
                    <Skeleton className="h-4 w-1/2" />
                    <Skeleton className="h-3 w-16" />
                  </div>
                ))
              ) : recentNotebooks.length === 0 ? (
                <div className="rounded-md border border-dashed border-border bg-muted/30 p-8 text-center">
                  <Book className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
                    No notebooks yet. Drop a PDF into Studio to start your first.
                  </p>
                  <Button
                    variant="default"
                    size="sm"
                    className="mt-3"
                    onClick={() => router.push('/studio')}
                  >
                    Open Studio
                  </Button>
                </div>
              ) : (
                recentNotebooks.map((nb) => (
                  <Link
                    key={nb.id}
                    href={`/notebooks/${nb.id}`}
                    className="group flex items-center justify-between rounded-md px-3 py-2 transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <Book className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary" />
                      <span className="truncate text-sm font-medium">
                        {nb.name}
                      </span>
                    </div>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {relativeTime(nb.updated ?? nb.created)}
                    </span>
                  </Link>
                ))
              )}
            </CardContent>
          </Card>
          </motion.div>

          {/* Hints strip */}
          <motion.div variants={item} className="rounded-md border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
            <FileText className="mr-1 inline h-3 w-3 align-text-bottom" />
            Tip: hit{' '}
            <kbd className="rounded border bg-background px-1 font-mono">⌘K</kbd>
            {' / '}
            <kbd className="rounded border bg-background px-1 font-mono">
              Ctrl+K
            </kbd>{' '}
            from anywhere to jump to a notebook, source, or action.
            <Database className="ml-3 mr-1 inline h-3 w-3 align-text-bottom" />
            All data lives in <code className="rounded bg-background px-1">~/.deeper-notebook/</code>.
          </motion.div>
        </motion.div>
      </div>
    </AppShell>
  )
}

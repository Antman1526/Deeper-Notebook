'use client'

// v0.8.97 — ExamLab: timed exam attempts over Evidence Studio quiz artifacts.
// (Idea adopted from PageLM; implementation original.)
//
// Three views in one panel, keyed on local state:
//   setup   — pick a notebook's quiz artifact + a duration, see recent scores
//   taking  — questions + countdown; submit is one-shot
//   results — score, per-question feedback, "Add missed to review deck"
//
// The countdown is display-only: the server stamped the deadline at start and
// grades late submissions as late instead of rejecting them, so a laggy timer
// can never eat an attempt.

import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlarmClock, CheckCircle2, XCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { studioApi } from '@/lib/api/studio'
import type { ExamAttempt } from '@/lib/api/study-exams'
import {
  useExamAttempt,
  useExamAttempts,
  useSeedExamMisses,
  useStartExam,
  useSubmitExam,
} from '@/lib/hooks/use-study-exams'
import { useNotebooks } from '@/lib/hooks/use-notebooks'

const DURATIONS = [
  { label: '10 min', sec: 600 },
  { label: '20 min', sec: 1200 },
  { label: '45 min', sec: 2700 },
  { label: '90 min', sec: 5400 },
] as const

function formatRemaining(deadlineIso: string, now: number): string {
  const remaining = Math.max(0, Math.floor((new Date(deadlineIso).getTime() - now) / 1000))
  const m = Math.floor(remaining / 60)
  const s = remaining % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export function ExamLab() {
  const [activeAttemptId, setActiveAttemptId] = useState<string | null>(null)
  const [notebookId, setNotebookId] = useState<string>('')
  const [artifactId, setArtifactId] = useState<string>('')
  const [durationSec, setDurationSec] = useState<number>(1200)
  const [answers, setAnswers] = useState<Record<string, string>>({})

  const notebooks = useNotebooks(false)
  const attempts = useExamAttempts(undefined, activeAttemptId === null)
  const attempt = useExamAttempt(activeAttemptId)
  const startExam = useStartExam()
  const submitExam = useSubmitExam()
  const seedMisses = useSeedExamMisses()

  // Quiz artifacts for the chosen notebook (completed ones only — a pending
  // generation has no questions yet).
  const artifacts = useQuery({
    queryKey: ['studio', 'artifacts', notebookId, 'for-examlab'],
    queryFn: () => studioApi.listArtifacts(notebookId),
    enabled: Boolean(notebookId),
  })
  const quizzes = useMemo(
    () => (artifacts.data ?? []).filter(
      (a) => a.artifact_type === 'quiz' && a.status === 'completed',
    ),
    [artifacts.data],
  )

  const current: ExamAttempt | undefined = attempt.data
  const taking = Boolean(current && current.submitted_at === null)
  const finished = Boolean(current && current.submitted_at !== null)

  // Tick once a second while taking, for the countdown display.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!taking) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [taking])

  const answeredCount = Object.keys(answers).length
  const missedCount = (current?.results ?? []).filter((r) => !r.correct).length
  const unseededMisses = (current?.results ?? []).filter(
    (r) => !r.correct && !(current?.seeded_indices ?? []).includes(r.index),
  ).length

  const startDisabled = !artifactId || startExam.isPending

  if (taking && current) {
    const overtime = new Date(current.deadline).getTime() <= now
    return (
      <Card data-testid="examlab-taking">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base">{current.title}</CardTitle>
              <CardDescription>
                {answeredCount} of {current.question_count} answered
              </CardDescription>
            </div>
            <p
              className={`flex items-center gap-1.5 font-mono text-sm ${overtime ? 'text-destructive' : 'text-muted-foreground'}`}
              role="timer"
              aria-label="Time remaining"
              data-testid="examlab-countdown"
            >
              <AlarmClock className="h-4 w-4" aria-hidden="true" />
              {overtime ? 'Overtime — still gradable' : formatRemaining(current.deadline, now)}
            </p>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {(current.questions ?? []).map((question) => (
            <fieldset key={question.index} className="space-y-2">
              <legend className="text-sm font-medium">
                {question.index + 1}. {question.prompt}
              </legend>
              <div className="space-y-1.5">
                {question.options.map((option) => (
                  <label
                    key={option.id}
                    className="flex cursor-pointer items-center gap-2 rounded-md border p-2 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5"
                  >
                    <input
                      type="radio"
                      name={`exam-q-${question.index}`}
                      value={option.id}
                      checked={answers[String(question.index)] === option.id}
                      onChange={() =>
                        setAnswers((prev) => ({ ...prev, [String(question.index)]: option.id }))
                      }
                    />
                    {option.text}
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
          <div className="flex items-center gap-3">
            <Button
              type="button"
              disabled={submitExam.isPending}
              data-testid="examlab-submit"
              onClick={() =>
                submitExam.mutate(
                  { attemptId: current.id, answers },
                  { onSuccess: () => setAnswers({}) },
                )
              }
            >
              Submit exam
            </Button>
            {answeredCount < current.question_count ? (
              <p className="text-xs text-muted-foreground">
                Unanswered questions are graded as incorrect.
              </p>
            ) : null}
          </div>
          {submitExam.isError ? (
            <p role="alert" className="text-sm text-destructive">
              Submission failed — your answers are still here. Try again.
            </p>
          ) : null}
        </CardContent>
      </Card>
    )
  }

  if (finished && current) {
    return (
      <Card data-testid="examlab-results">
        <CardHeader>
          <CardTitle className="text-base">
            {current.title} — {current.score_percent}%
          </CardTitle>
          <CardDescription>
            {current.correct_count} of {current.question_count} correct
            {current.late ? ' · submitted after time' : ''}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            {missedCount > 0 ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={unseededMisses === 0 || seedMisses.isPending}
                data-testid="examlab-seed-misses"
                onClick={() => seedMisses.mutate(current.id)}
              >
                {unseededMisses === 0
                  ? 'Missed questions added to review deck'
                  : `Add ${unseededMisses} missed to review deck`}
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setActiveAttemptId(null)}
            >
              Back to ExamLab
            </Button>
          </div>
          <ol className="space-y-3">
            {(current.results ?? []).map((result) => (
              <li key={result.index} className="rounded-md border p-3 text-sm">
                <p className="flex items-start gap-2 font-medium">
                  {result.correct ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                  ) : (
                    <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
                  )}
                  {result.index + 1}. {result.prompt}
                </p>
                <div className="mt-1.5 space-y-0.5 pl-6 text-muted-foreground">
                  {!result.correct ? (
                    <p>
                      {result.answered
                        ? `Your answer: ${result.options.find((o) => o.id === result.selected_option_id)?.text ?? '—'}`
                        : 'Not answered'}
                    </p>
                  ) : null}
                  <p>
                    Correct: {result.options.find((o) => o.id === result.correct_option_id)?.text}
                  </p>
                  {result.explanation ? <p>{result.explanation}</p> : null}
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    )
  }

  // Setup view.
  return (
    /* v0.8.98 — no CardHeader: StudyWorkbench already renders an "ExamLab"
       section heading and description directly above this card. A card title
       repeated the name and a second description restated the same sentence.
       The sibling "Active study plans" section sets the house pattern —
       section heading, then unlabelled content cards. */
    <Card data-testid="examlab-setup">
      <CardContent className="space-y-4 pt-6">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Notebook</span>
            <select
              className="w-full rounded-md border bg-transparent p-2"
              value={notebookId}
              data-testid="examlab-notebook-select"
              onChange={(e) => {
                setNotebookId(e.target.value)
                setArtifactId('')
              }}
            >
              <option value="">Choose a notebook…</option>
              {(notebooks.data ?? []).map((notebook) => (
                <option key={notebook.id} value={notebook.id}>
                  {notebook.name}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Quiz</span>
            <select
              className="w-full rounded-md border bg-transparent p-2"
              value={artifactId}
              disabled={!notebookId}
              data-testid="examlab-quiz-select"
              onChange={(e) => setArtifactId(e.target.value)}
            >
              <option value="">
                {!notebookId
                  ? 'Pick a notebook first'
                  : artifacts.isLoading
                    ? 'Loading quizzes…'
                    : quizzes.length === 0
                      ? 'No completed quizzes — generate one in Studio'
                      : 'Choose a quiz…'}
              </option>
              {quizzes.map((quiz) => (
                <option key={quiz.id} value={quiz.id}>
                  {quiz.title}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Exam duration">
          {DURATIONS.map((duration) => (
            <Button
              key={duration.sec}
              type="button"
              size="sm"
              variant={durationSec === duration.sec ? 'secondary' : 'outline'}
              aria-pressed={durationSec === duration.sec}
              onClick={() => setDurationSec(duration.sec)}
            >
              {duration.label}
            </Button>
          ))}
        </div>
        <Button
          type="button"
          disabled={startDisabled}
          data-testid="examlab-start"
          onClick={() =>
            startExam.mutate(
              { artifactId, durationSec },
              {
                onSuccess: (created) => {
                  setAnswers({})
                  setActiveAttemptId(created.id)
                },
              },
            )
          }
        >
          Start timed exam
        </Button>
        {startExam.isError ? (
          <p role="alert" className="text-sm text-destructive">
            Could not start the exam. If this quiz predates structured documents,
            regenerate it in Evidence Studio first.
          </p>
        ) : null}

        {(attempts.data ?? []).length > 0 ? (
          <div className="space-y-2 border-t pt-3">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Recent attempts
            </p>
            <ul className="space-y-1.5">
              {(attempts.data ?? []).slice(0, 5).map((summary) => (
                <li key={summary.id}>
                  <button
                    type="button"
                    className="w-full rounded-md border p-2 text-left text-sm hover:bg-muted/50"
                    onClick={() => setActiveAttemptId(summary.id)}
                  >
                    <span className="font-medium">{summary.title}</span>
                    <span className="text-muted-foreground">
                      {' — '}
                      {summary.submitted_at
                        ? `${summary.score_percent}% (${summary.correct_count}/${summary.question_count})${summary.late ? ' · late' : ''}`
                        : 'in progress'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

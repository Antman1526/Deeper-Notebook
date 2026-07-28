'use client'

import { useEffect, useMemo, useState } from 'react'
import { Check, ChevronLeft, ChevronRight, RotateCcw, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { MindMapArtifactViewer, type MindMapArtifactNode } from './MindMapArtifactViewer'

interface Flashcard {
  front: string
  back: string
  source?: string
}

interface QuizOption {
  key: string
  text: string
}

interface QuizQuestion {
  question: string
  options: QuizOption[]
  answerKey: string
  explanation?: string
  source?: string
}

interface ResearchRunSection {
  title: string
  body: string[]
}

type DataTableRow = Record<string, string>

export type MindMapNode = MindMapArtifactNode

interface CoursePackModule {
  title: string
  markdown: string
  summary: string
  hasFacilitatorNotes: boolean
}

export interface CoursePackProgress {
  selected_index: number
  completed_modules: Record<string, boolean>
  mode: 'learner' | 'facilitator'
}

export interface FlashcardProgress {
  index: number
  revealed: boolean
}

export interface QuizProgress {
  index: number
  answers: Record<string, string>
}

export interface StudyProgress {
  version: 1
  content_fingerprint: string
  course_pack?: CoursePackProgress
  flashcards?: FlashcardProgress
  quiz?: QuizProgress
  updated_at: string
}

function stripMarkdown(value: string): string {
  return value
    .replace(/^#+\s*/, '')
    .replace(/^\s*[-*]\s*/, '')
    .replace(/\*\*/g, '')
    .trim()
}

function readLabel(line: string, labels: string[]): string | null {
  const normalized = stripMarkdown(line)
  for (const label of labels) {
    const pattern = new RegExp(`^${label}\\s*:\\s*(.+)$`, 'i')
    const match = normalized.match(pattern)
    if (match?.[1]) return match[1].trim()
  }
  return null
}

function splitSections(markdown: string, headingPattern: RegExp): string[][] {
  const sections: string[][] = []
  let current: string[] = []

  for (const line of markdown.split(/\r?\n/)) {
    if (headingPattern.test(line)) {
      if (current.length > 0) sections.push(current)
      current = [line]
    } else if (current.length > 0) {
      current.push(line)
    }
  }

  if (current.length > 0) sections.push(current)
  return sections
}

export function parseFlashcards(markdown: string): Flashcard[] {
  const sections = splitSections(markdown, /^#{2,4}\s*(?:card|flashcard)\b/i)
  const cards: Flashcard[] = []

  for (const section of sections) {
    let front = ''
    let back = ''
    let source = ''

    for (const line of section) {
      front ||= readLabel(line, ['front', 'question', 'q']) ?? ''
      back ||= readLabel(line, ['back', 'answer', 'a']) ?? ''
      source ||= readLabel(line, ['source', 'citation']) ?? ''
    }

    if (front && back) {
      cards.push(source ? { front, back, source } : { front, back })
    }
  }

  return cards
}

export function parseQuizQuestions(markdown: string): QuizQuestion[] {
  const sections = splitSections(markdown, /^#{2,4}\s*question\b/i)
  const questions: QuizQuestion[] = []

  for (const section of sections) {
    let question = ''
    let answerKey = ''
    let explanation = ''
    let source = ''
    const options: QuizOption[] = []

    for (const rawLine of section) {
      const line = stripMarkdown(rawLine)
      if (!line || /^question\s*\d*$/i.test(line)) continue

      const optionMatch = line.match(/^([A-H])[\).]\s+(.+)$/i)
      if (optionMatch?.[1] && optionMatch[2]) {
        options.push({
          key: optionMatch[1].toUpperCase(),
          text: optionMatch[2].trim(),
        })
        continue
      }

      answerKey ||= readLabel(line, ['answer', 'correct answer', 'correct']) ?? ''
      explanation ||= readLabel(line, ['explanation', 'why']) ?? ''
      source ||= readLabel(line, ['source', 'citation']) ?? ''

      if (!question && !answerKey && !explanation && !source) {
        question = line
      }
    }

    const normalizedAnswer = answerKey.trim().slice(0, 1).toUpperCase()
    if (question && options.length > 0 && normalizedAnswer) {
      questions.push({
        question,
        options,
        answerKey: normalizedAnswer,
        ...(explanation ? { explanation } : {}),
        ...(source ? { source } : {}),
      })
    }
  }

  return questions
}

export function parseResearchRunSections(markdown: string): ResearchRunSection[] {
  return splitSections(markdown, /^#{2,4}\s+/)
    .map((section) => {
      const [heading, ...bodyLines] = section
      const body = bodyLines
        .map(stripMarkdown)
        .filter(Boolean)
      return {
        title: stripMarkdown(heading ?? ''),
        body,
      }
    })
    .filter((section) => section.title && section.body.length > 0)
}

export function normalizeResearchRunStages(stages: unknown): ResearchRunSection[] {
  if (!Array.isArray(stages)) return []

  return stages
    .map((stage) => {
      if (!stage || typeof stage !== 'object') return null
      const record = stage as Record<string, unknown>
      const title = typeof record.title === 'string' ? record.title.trim() : ''
      const rawItems = Array.isArray(record.items) ? record.items : []
      const body = rawItems
        .filter((item): item is string => typeof item === 'string')
        .map((item) => item.trim())
        .filter(Boolean)
      return title && body.length > 0 ? { title, body } : null
    })
    .filter((stage): stage is ResearchRunSection => stage !== null)
}

function splitMarkdownTableRow(line: string): string[] {
  const trimmed = line.trim()
  if (!trimmed.startsWith('|') || !trimmed.endsWith('|')) return []
  return trimmed
    .slice(1, -1)
    .split('|')
    .map(stripMarkdown)
}

function isMarkdownTableSeparator(cells: string[]): boolean {
  return cells.length > 0
    && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, '')))
}

export function parseDataTableRows(markdown: string): DataTableRow[] {
  let header: string[] = []
  const rows: DataTableRow[] = []

  for (const line of markdown.split(/\r?\n/)) {
    const cells = splitMarkdownTableRow(line)
    if (cells.length === 0) {
      if (rows.length > 0) break
      continue
    }
    if (isMarkdownTableSeparator(cells)) continue
    if (header.length === 0) {
      header = cells.map((cell, index) => cell || `Column ${index + 1}`)
      continue
    }
    const row = Object.fromEntries(
      cells.map((cell, index) => [header[index] || `Column ${index + 1}`, cell]),
    )
    if (Object.values(row).some(Boolean)) rows.push(row)
  }

  return rows
}

export function normalizeDataTableRows(rows: unknown): DataTableRow[] {
  if (!Array.isArray(rows)) return []
  return rows
    .map((row) => {
      if (!row || typeof row !== 'object') return null
      const normalized = Object.fromEntries(
        Object.entries(row as Record<string, unknown>)
          .filter(([key]) => key.trim().length > 0)
          .map(([key, value]) => [key, value == null ? '' : String(value)]),
      )
      return Object.keys(normalized).length > 0 ? normalized : null
    })
    .filter((row): row is DataTableRow => row !== null)
}

export function parseMindMap(markdown: string): MindMapNode[] {
  const roots: MindMapNode[] = []
  const stack: Array<{ level: number; node: MindMapNode }> = []

  for (const line of markdown.split(/\r?\n/)) {
    const match = line.match(/^(\s*)[-*]\s+(.+)$/)
    if (!match?.[2]) continue

    const level = Math.floor((match[1]?.replace(/\t/g, '  ').length ?? 0) / 2)
    const rawLabel = stripMarkdown(match[2])
    const citations = Array.from(rawLabel.matchAll(/\[S\d+\]/g), (citation) => citation[0])
    const withoutCitations = rawLabel.replace(/\s*\[S\d+\]/g, '').trim()
    const relationshipMatch = withoutCitations.match(/^(.*)\s+\(([^()]+)\)$/)

    while (stack.length > 0 && stack[stack.length - 1].level >= level) {
      stack.pop()
    }

    const parent = stack[stack.length - 1]?.node
    const siblingIndex = parent ? parent.children.length : roots.length
    const id = parent ? `${parent.id}/${siblingIndex}` : String(siblingIndex)
    const node: MindMapNode = {
      id,
      label: relationshipMatch?.[1]?.trim() || withoutCitations,
      relationship: relationshipMatch?.[2]?.trim() || '',
      citations,
      children: [],
    }
    if (parent) parent.children.push(node)
    else roots.push(node)
    stack.push({ level, node })
  }

  return roots
}

function moduleSummary(section: string[]): string {
  const summary = section
    .slice(1)
    .map(stripMarkdown)
    .find((line) => {
      return Boolean(line)
        && !/^duration\s*:/i.test(line)
        && !/^(facilitator|instructor)\s+notes?\s*:/i.test(line)
    })
  return summary ?? 'Module details and activities'
}

export function parseCoursePackModules(markdown: string): CoursePackModule[] {
  const moduleSections = splitSections(
    markdown,
    /^#{2,4}\s*(?:module|lesson block|lesson)\s*\d*(?:[:\-.]\s*)?/i,
  )
  const fallbackSections = moduleSections.length > 0
    ? moduleSections
    : splitSections(markdown, /^##\s+/).filter((section) => {
        const title = stripMarkdown(section[0] ?? '')
        return !/^(audience|learning outcomes?|prerequisites?|module roadmap|source readiness|follow-up resources?)$/i.test(title)
      })

  return fallbackSections
    .map((section, index) => {
      const title = stripMarkdown(section[0] ?? '') || `Module ${index + 1}`
      const markdownSection = section.join('\n').trim()
      return {
        title,
        markdown: markdownSection,
        summary: moduleSummary(section),
        hasFacilitatorNotes: /(facilitator notes?|instructor notes?|demo script)/i.test(markdownSection),
      }
    })
    .filter((module) => module.markdown.length > 0)
}

function learnerMarkdown(markdown: string): string {
  const lines = markdown.split(/\r?\n/)
  const visible: string[] = []
  let hidingFacilitatorSection = false

  for (const line of lines) {
    const isHeading = /^#{2,6}\s+/.test(line)
    if (isHeading) {
      hidingFacilitatorSection = /(facilitator notes?|instructor notes?|demo script)/i.test(line)
    }
    if (!hidingFacilitatorSection) visible.push(line)
  }

  return visible.join('\n').trim()
}

function clampIndex(value: unknown, maxExclusive: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || maxExclusive <= 0) {
    return 0
  }
  return Math.min(Math.max(0, Math.trunc(value)), maxExclusive - 1)
}

export function CoursePackViewer({
  markdown,
  progress,
  onProgressChange,
}: {
  markdown: string
  progress?: CoursePackProgress
  onProgressChange?: (progress: CoursePackProgress) => void
}) {
  const modules = useMemo(() => parseCoursePackModules(markdown), [markdown])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [mode, setMode] = useState<'learner' | 'facilitator'>('learner')
  const [checkedModules, setCheckedModules] = useState<Record<string, boolean>>({})

  useEffect(() => {
    setSelectedIndex(clampIndex(progress?.selected_index, modules.length))
    setMode(progress?.mode === 'facilitator' ? 'facilitator' : 'learner')
    setCheckedModules(progress?.completed_modules ?? {})
  }, [markdown, modules.length, progress])

  if (modules.length === 0) {
    return (
      <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none break-words prose-headings:font-semibold prose-p:leading-7">
        <ReactMarkdown>{markdown}</ReactMarkdown>
      </div>
    )
  }

  const selectedModule = modules[Math.min(selectedIndex, modules.length - 1)]
  const completedCount = modules.filter((module) => checkedModules[module.title]).length
  const visibleMarkdown = mode === 'facilitator'
    ? selectedModule.markdown
    : learnerMarkdown(selectedModule.markdown)

  function toggleModule(title: string, checked: boolean) {
    setCheckedModules((current) => {
      const next = {
      ...current,
      [title]: checked,
      }
      onProgressChange?.({
        selected_index: selectedIndex,
        completed_modules: next,
        mode,
      })
      return next
    })
  }

  function selectModule(nextIndex: number) {
    setSelectedIndex(nextIndex)
    onProgressChange?.({
      selected_index: nextIndex,
      completed_modules: checkedModules,
      mode,
    })
  }

  function changeMode(nextMode: 'learner' | 'facilitator') {
    setMode(nextMode)
    onProgressChange?.({
      selected_index: selectedIndex,
      completed_modules: checkedModules,
      mode: nextMode,
    })
  }

  return (
    <section className="rounded-md border bg-background p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium">Course Pack workspace</div>
          <div className="mt-1 text-xs text-muted-foreground">
            Navigate modules, track progress, and switch between learner and facilitator views.
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-[0.68rem]">
            {modules.length} {modules.length === 1 ? 'module' : 'modules'}
          </Badge>
          <Badge variant="secondary" className="text-[0.68rem]">
            {completedCount} complete
          </Badge>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2" role="group" aria-label="Course Pack view mode">
        <Button
          type="button"
          size="sm"
          variant={mode === 'learner' ? 'default' : 'outline'}
          onClick={() => changeMode('learner')}
        >
          Learner view
        </Button>
        <Button
          type="button"
          size="sm"
          variant={mode === 'facilitator' ? 'default' : 'outline'}
          onClick={() => changeMode('facilitator')}
        >
          Facilitator notes
        </Button>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="rounded-md border bg-muted/30 p-3">
          <div className="text-sm font-medium">Module checklist</div>
          <div className="mt-3 space-y-2">
            {modules.map((module, index) => {
              const checkboxId = `course-pack-module-${index}`
              return (
                <div
                  key={module.title}
                  className={cn(
                    'rounded-md border bg-background px-2 py-2',
                    index === selectedIndex && 'border-[var(--dn-accent-strong)]',
                  )}
                >
                  <div className="flex items-start gap-2">
                    <input
                      id={checkboxId}
                      type="checkbox"
                      checked={checkedModules[module.title] === true}
                      aria-label={`Mark ${module.title} complete`}
                      onChange={(event) => toggleModule(module.title, event.target.checked)}
                      className="mt-1 h-4 w-4 rounded border-border"
                    />
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      aria-current={index === selectedIndex ? 'true' : undefined}
                      onClick={() => selectModule(index)}
                    >
                      <span className="block text-sm font-medium">{module.title}</span>
                      <span className="mt-1 line-clamp-2 block text-xs leading-5 text-muted-foreground">
                        {module.summary}
                      </span>
                    </button>
                  </div>
                  {module.hasFacilitatorNotes && (
                    <Badge variant="outline" className="mt-2 text-[0.68rem]">
                      Facilitator ready
                    </Badge>
                  )}
                </div>
              )
            })}
          </div>
        </aside>

        <article className="min-w-0 rounded-md border bg-muted/20 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-medium">{selectedModule.title}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {mode === 'facilitator'
                  ? 'Instructor notes and delivery guidance are visible.'
                  : 'Facilitator-only notes are hidden for learner handouts.'}
              </div>
            </div>
            <Badge variant="outline" className="text-[0.68rem]">
              Module {Math.min(selectedIndex, modules.length - 1) + 1}
            </Badge>
          </div>
          <div className="prose prose-sm prose-neutral dark:prose-invert mt-4 max-w-none break-words prose-headings:font-semibold prose-p:leading-7">
            <ReactMarkdown>{visibleMarkdown || selectedModule.markdown}</ReactMarkdown>
          </div>
        </article>
      </div>
    </section>
  )
}

export function DataTableViewer({
  markdown,
  rows,
}: {
  markdown: string
  rows?: unknown
}) {
  const normalizedRows = useMemo(() => normalizeDataTableRows(rows), [rows])
  const parsedRows = useMemo(() => parseDataTableRows(markdown), [markdown])
  const tableRows = normalizedRows.length > 0 ? normalizedRows : parsedRows
  const headers = useMemo(() => {
    const keys: string[] = []
    for (const row of tableRows) {
      for (const key of Object.keys(row)) {
        if (!keys.includes(key)) keys.push(key)
      }
    }
    return keys
  }, [tableRows])

  if (tableRows.length === 0 || headers.length === 0) {
    return (
      <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none break-words prose-headings:font-semibold prose-p:leading-7">
        <ReactMarkdown>{markdown}</ReactMarkdown>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-semibold">Data table</div>
        <div className="text-xs text-muted-foreground">
          {tableRows.length} {tableRows.length === 1 ? 'row' : 'rows'} extracted from source-grounded output.
        </div>
      </div>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[42rem] border-collapse text-left text-sm">
          <thead className="bg-muted/60">
            <tr>
              {headers.map((header) => (
                <th
                  key={header}
                  scope="col"
                  className="border-b px-3 py-2 text-xs font-semibold uppercase tracking-normal text-muted-foreground"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row, rowIndex) => (
              <tr key={`data-table-row-${rowIndex}`} className="odd:bg-background even:bg-muted/20">
                {headers.map((header) => (
                  <td key={`${rowIndex}-${header}`} className="align-top border-b px-3 py-2">
                    {row[header] || '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function MindMapViewer({
  markdown,
  artifactId,
  notebookId,
}: {
  markdown: string
  artifactId?: string
  notebookId?: string
}) {
  const nodes = useMemo(() => parseMindMap(markdown), [markdown])
  const nodeCount = useMemo(() => {
    const countNodes = (items: MindMapNode[]): number =>
      items.reduce((total, item) => total + 1 + countNodes(item.children), 0)
    return countNodes(nodes)
  }, [nodes])

  if (nodes.length === 0) {
    return (
      <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none break-words prose-headings:font-semibold prose-p:leading-7">
        <ReactMarkdown>{markdown}</ReactMarkdown>
      </div>
    )
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">Mind map</div>
          <div className="text-xs text-muted-foreground">
            {nodeCount} {nodeCount === 1 ? 'node' : 'nodes'} arranged from the source-grounded outline.
          </div>
        </div>
        <Badge variant="outline" className="text-[0.68rem]">
          {nodes.length} {nodes.length === 1 ? 'root' : 'roots'}
        </Badge>
      </div>
      <MindMapArtifactViewer nodes={nodes} artifactId={artifactId} notebookId={notebookId} />
    </section>
  )
}

export function FlashcardDeck({
  markdown,
  progress,
  onProgressChange,
}: {
  markdown: string
  progress?: FlashcardProgress
  onProgressChange?: (progress: FlashcardProgress) => void
}) {
  const cards = useMemo(() => parseFlashcards(markdown), [markdown])
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    setIndex(clampIndex(progress?.index, cards.length))
    setRevealed(progress?.revealed === true)
  }, [markdown, cards.length, progress])

  if (cards.length === 0) return null

  const card = cards[index]
  const hasPrevious = index > 0
  const hasNext = index < cards.length - 1

  function move(nextIndex: number) {
    setIndex(nextIndex)
    setRevealed(false)
    onProgressChange?.({ index: nextIndex, revealed: false })
  }

  function toggleReveal() {
    setRevealed((current) => {
      const next = !current
      onProgressChange?.({ index, revealed: next })
      return next
    })
  }

  return (
    <section className="rounded-md border bg-background p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium">Flashcard review</div>
          <div className="text-xs text-muted-foreground">
            Card {index + 1} of {cards.length}
          </div>
        </div>
        <Badge variant="outline" className="text-[0.68rem]">
          {cards.length} cards
        </Badge>
      </div>

      <div className="mt-4 rounded-md border bg-muted/30 p-4">
        <div className="text-xs font-medium uppercase text-muted-foreground">Prompt</div>
        <div className="mt-2 text-base font-medium leading-7">{card.front}</div>
        {revealed && (
          <div className="mt-4 border-t pt-4">
            <div className="text-xs font-medium uppercase text-muted-foreground">Answer</div>
            <div className="mt-2 text-sm leading-6">{card.back}</div>
            {card.source && (
              <div className="mt-3 text-xs text-muted-foreground">Source: {card.source}</div>
            )}
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!hasPrevious}
          onClick={() => move(index - 1)}
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          Previous card
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={toggleReveal}
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          {revealed ? 'Hide answer' : 'Reveal answer'}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!hasNext}
          onClick={() => move(index + 1)}
        >
          Next card
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </section>
  )
}

export function ResearchRunViewer({
  markdown,
  stages,
}: {
  markdown: string
  stages?: unknown
}) {
  const { sections, stageSourceLabel } = useMemo(() => {
    const structuredSections = normalizeResearchRunStages(stages)
    if (structuredSections.length > 0) {
      return {
        sections: structuredSections,
        stageSourceLabel: 'Structured metadata',
      }
    }
    return {
      sections: parseResearchRunSections(markdown),
      stageSourceLabel: 'Parsed markdown',
    }
  }, [markdown, stages])

  if (sections.length === 0) {
    return (
      <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none break-words prose-headings:font-semibold prose-p:leading-7">
        <ReactMarkdown>{markdown}</ReactMarkdown>
      </div>
    )
  }

  return (
    <section className="rounded-md border bg-background p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium">Research run workspace</div>
          <div className="mt-1 text-xs text-muted-foreground">
            Staged investigation summary from the generated artifact.
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-[0.68rem]">
            {sections.length} {sections.length === 1 ? 'stage' : 'stages'}
          </Badge>
          <Badge variant="secondary" className="text-[0.68rem]">
            {stageSourceLabel}
          </Badge>
        </div>
      </div>

      <div className="mt-4 grid gap-3">
        {sections.map((section) => (
          <article key={section.title} className="rounded-md border bg-muted/30 p-3">
            <div className="text-sm font-medium">{section.title}</div>
            <ul className="mt-2 space-y-1.5 text-sm leading-6 text-muted-foreground">
              {section.body.map((line, index) => (
                <li key={`${section.title}-${index}`}>{line}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  )
}

export function QuizRunner({
  markdown,
  progress,
  onProgressChange,
}: {
  markdown: string
  progress?: QuizProgress
  onProgressChange?: (progress: QuizProgress) => void
}) {
  const questions = useMemo(() => parseQuizQuestions(markdown), [markdown])
  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<number, string>>({})

  useEffect(() => {
    setIndex(clampIndex(progress?.index, questions.length))
    const nextAnswers: Record<number, string> = {}
    for (const [questionIndex, answerKey] of Object.entries(progress?.answers ?? {})) {
      const parsedIndex = Number(questionIndex)
      if (Number.isInteger(parsedIndex) && typeof answerKey === 'string') {
        nextAnswers[parsedIndex] = answerKey
      }
    }
    setAnswers(nextAnswers)
  }, [markdown, questions.length, progress])

  if (questions.length === 0) return null

  const question = questions[index]
  const selected = answers[index]
  const answeredCount = Object.keys(answers).length
  const score = questions.reduce((total, item, questionIndex) => {
    return answers[questionIndex] === item.answerKey ? total + 1 : total
  }, 0)

  function chooseAnswer(answerKey: string) {
    setAnswers((current) => {
      const next = { ...current, [index]: answerKey }
      onProgressChange?.({
        index,
        answers: Object.fromEntries(
          Object.entries(next).map(([questionIndex, value]) => [String(questionIndex), value]),
        ),
      })
      return next
    })
  }

  function moveQuestion(nextIndex: number) {
    setIndex(nextIndex)
    onProgressChange?.({
      index: nextIndex,
      answers: Object.fromEntries(
        Object.entries(answers).map(([questionIndex, value]) => [String(questionIndex), value]),
      ),
    })
  }

  return (
    <section className="rounded-md border bg-background p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium">Quiz runner</div>
          <div className="text-xs text-muted-foreground">
            Question {index + 1} of {questions.length}
          </div>
        </div>
        <Badge variant="outline" className="text-[0.68rem]">
          Score: {score} / {answeredCount || questions.length}
        </Badge>
      </div>

      <div className="mt-4 text-base font-medium leading-7">{question.question}</div>
      <div className="mt-3 grid gap-2">
        {question.options.map((option) => {
          const isSelected = selected === option.key
          const isCorrect = selected && option.key === question.answerKey
          const isWrong = isSelected && option.key !== question.answerKey
          return (
            <button
              key={option.key}
              type="button"
              aria-label={`${option.key}. ${option.text}`}
              onClick={() => chooseAnswer(option.key)}
              className={cn(
                'flex items-start gap-2 rounded-md border bg-muted/30 px-3 py-2 text-left text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                isCorrect && 'border-[var(--dn-success)] bg-[var(--dn-success-soft)]',
                isWrong && 'border-destructive bg-destructive/10',
              )}
            >
              <span className="font-medium">{option.key}.</span>
              <span className="min-w-0 flex-1">{option.text}</span>
              {isCorrect && <Check className="h-4 w-4 text-[var(--dn-success)]" aria-hidden="true" />}
              {isWrong && <X className="h-4 w-4 text-destructive" aria-hidden="true" />}
            </button>
          )
        })}
      </div>

      {selected && (
        <div className="mt-4 rounded-md border bg-muted/30 p-3 text-sm">
          <div className="font-medium">
            {selected === question.answerKey ? 'Correct' : `Correct answer: ${question.answerKey}`}
          </div>
          {question.explanation && (
            <div className="mt-2 leading-6 text-muted-foreground">{question.explanation}</div>
          )}
          {question.source && (
            <div className="mt-2 text-xs text-muted-foreground">Source: {question.source}</div>
          )}
        </div>
      )}

      {questions.length > 1 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={index === 0}
            onClick={() => moveQuestion(index - 1)}
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            Previous question
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={index === questions.length - 1}
            onClick={() => moveQuestion(index + 1)}
          >
            Next question
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      )}
    </section>
  )
}

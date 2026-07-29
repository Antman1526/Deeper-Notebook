import { syntaxTree } from '@codemirror/language'
import type { Extension, EditorState, Text } from '@codemirror/state'
import {
  Decoration,
  type DecorationSet,
  EditorView,
  ViewPlugin,
  WidgetType,
} from '@codemirror/view'

import type { VaultLink } from '@/lib/api/vault'
import type { MarkdownConstructKind } from '@/lib/vault/markdown-model'
import {
  buildUniqueResolvedSpanMap,
  createMarkdownSourceIndex,
  vaultLinkSpanKey,
} from '@/lib/vault/remark-vault-links'

interface SourceRange {
  from: number
  to: number
}

interface PreviewSourceContext {
  mathRanges: SourceRange[]
  sourceIndex: Pick<ReturnType<typeof createMarkdownSourceIndex>, 'byteOffset'>
}

interface PreviewDocumentContext extends PreviewSourceContext {
  resolvedSpans: Map<string, VaultLink>
}

export interface PreviewDecorationRecord {
  kind: string
  from: number
  to: number
  decoration: Decoration
  atomic?: boolean
}

export interface LivePreviewOptions {
  links?: VaultLink[]
  onNavigate?: (noteId: string) => void
  source?: string
}

const parserKinds: Partial<Record<string, MarkdownConstructKind>> = {
  Emphasis: 'emphasis',
  StrongEmphasis: 'strong',
  Strikethrough: 'strikethrough',
  InlineCode: 'inline-code',
  FencedCode: 'fenced-code',
  Link: 'link',
  TaskMarker: 'task-marker',
  Blockquote: 'blockquote',
  HorizontalRule: 'horizontal-rule',
  ListMark: 'list-marker',
}

const attachmentExtension = /\.(?:png|jpe?g|gif|webp|svg|pdf|mp3|mp4|mov)$/i
const scannerLookaround = 2_052
const constructReadLimit = 4_096
const sourceContextCache = new WeakMap<
  Text,
  Map<string | undefined, PreviewSourceContext>
>()

function intersects(left: SourceRange, right: SourceRange): boolean {
  return left.from < right.to && right.from < left.to
}

function visibleRanges(state: EditorState, ranges: readonly SourceRange[]): SourceRange[] {
  const normalized = ranges
    .map(({ from, to }) => ({
      from: Math.max(0, Math.min(from, state.doc.length)),
      to: Math.max(0, Math.min(to, state.doc.length)),
    }))
    .filter((range) => range.to > range.from)
    .sort((left, right) => left.from - right.from || left.to - right.to)
  const merged: SourceRange[] = []

  for (const range of normalized) {
    const previous = merged.at(-1)
    if (!previous || previous.to < range.from) merged.push(range)
    else previous.to = Math.max(previous.to, range.to)
  }
  return merged
}

function isVisible(range: SourceRange, ranges: readonly SourceRange[]): boolean {
  return ranges.some((visible) => intersects(range, visible))
}

function selectionIntersects(state: EditorState, construct: SourceRange): boolean {
  return state.selection.ranges.some((selection) => selection.empty
    ? selection.from >= construct.from && selection.from < construct.to
    : selection.from < construct.to && construct.from < selection.to)
}

function rangeIsSingleLine(state: EditorState, range: SourceRange): boolean {
  return range.to > range.from
    && state.doc.lineAt(range.from).number === state.doc.lineAt(range.to - 1).number
}

function scannerRanges(state: EditorState, ranges: readonly SourceRange[]): SourceRange[] {
  return ranges.map((range) => {
    const firstLine = state.doc.lineAt(range.from)
    const lastLine = state.doc.lineAt(Math.max(range.from, range.to - 1))
    return {
      from: Math.max(firstLine.from, range.from - scannerLookaround),
      to: Math.min(lastLine.to, range.to + scannerLookaround),
    }
  })
}

function collectMatches(
  doc: Text,
  ranges: readonly SourceRange[],
  expression: RegExp,
): SourceRange[] {
  const matches: SourceRange[] = []
  const seen = new Set<string>()
  for (const range of ranges) {
    const scoped = doc.sliceString(range.from, range.to)
    expression.lastIndex = 0
    for (const match of scoped.matchAll(expression)) {
      const from = range.from + (match.index || 0)
      const to = from + match[0].length
      const key = `${from}:${to}`
      if (!seen.has(key)) {
        seen.add(key)
        matches.push({ from, to })
      }
    }
  }
  return matches.sort((left, right) => left.from - right.from || left.to - right.to)
}

function indexMathRanges(source: string): SourceRange[] {
  return [...source.matchAll(/(?<!\\)\$(?:[^$\\\r\n]|\\.)+\$/gu)]
    .map((match) => {
      const from = match.index
      return { from, to: from + match[0].length }
    })
}

function indexedIntersections(
  indexed: readonly SourceRange[],
  visible: readonly SourceRange[],
): SourceRange[] {
  const intersections: SourceRange[] = []
  const seen = new Set<string>()
  for (const viewport of visible) {
    let low = 0
    let high = indexed.length
    while (low < high) {
      const middle = Math.floor((low + high) / 2)
      if (indexed[middle].to <= viewport.from) low = middle + 1
      else high = middle
    }
    for (let index = low; index < indexed.length; index += 1) {
      const range = indexed[index]
      if (range.from >= viewport.to) break
      const key = `${range.from}:${range.to}`
      if (!seen.has(key)) {
        seen.add(key)
        intersections.push(range)
      }
    }
  }
  return intersections.sort((left, right) => left.from - right.from || left.to - right.to)
}

function visibleIntersections(
  range: SourceRange,
  visible: readonly SourceRange[],
): SourceRange[] {
  const intersections: SourceRange[] = []
  for (const viewport of visible) {
    const from = Math.max(range.from, viewport.from)
    const to = Math.min(range.to, viewport.to)
    if (to > from) intersections.push({ from, to })
  }
  return intersections
}

function isFullyVisible(range: SourceRange, visible: readonly SourceRange[]): boolean {
  return visible.some((viewport) =>
    range.from >= viewport.from && range.to <= viewport.to,
  )
}

function mergeRanges(ranges: readonly SourceRange[]): SourceRange[] {
  const merged: SourceRange[] = []
  for (const range of [...ranges].sort(
    (left, right) => left.from - right.from || left.to - right.to,
  )) {
    const previous = merged.at(-1)
    if (!previous || previous.to < range.from) merged.push({ ...range })
    else previous.to = Math.max(previous.to, range.to)
  }
  return merged
}

function containedBy(range: SourceRange, candidates: readonly SourceRange[]): boolean {
  let low = 0
  let high = candidates.length - 1
  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    const candidate = candidates[middle]
    if (candidate.from > range.from) high = middle - 1
    else if (candidate.to < range.to) low = middle + 1
    else return true
  }
  return false
}

function overlapsSorted(range: SourceRange, candidates: readonly SourceRange[]): boolean {
  let low = 0
  let high = candidates.length - 1
  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    const candidate = candidates[middle]
    if (candidate.to <= range.from) low = middle + 1
    else if (candidate.from >= range.to) high = middle - 1
    else return true
  }
  return false
}

function sourceText(state: EditorState, range: SourceRange): string {
  return state.doc.sliceString(range.from, range.to)
}

function pairedMarker(
  state: EditorState,
  range: SourceRange,
  expression: RegExp,
): string | undefined {
  const prefix = state.doc.sliceString(
    range.from,
    Math.min(range.to, range.from + constructReadLimit),
  )
  const marker = expression.exec(prefix)?.[0]
  if (!marker || range.to - range.from < marker.length * 2) return undefined
  const suffix = state.doc.sliceString(
    Math.max(range.from, range.to - constructReadLimit),
    range.to,
  )
  return suffix.endsWith(marker) ? marker : undefined
}

function linePrefixFragment(
  state: EditorState,
  range: SourceRange,
  position: number,
  limit = constructReadLimit,
): { from: number; value: string } {
  const line = state.doc.lineAt(position)
  const from = Math.max(range.from, line.from)
  const to = Math.min(range.to, line.to, from + limit)
  return { from, value: state.doc.sliceString(from, to) }
}

function visibleLinePrefixFragments(
  state: EditorState,
  range: SourceRange,
  visible: readonly SourceRange[],
): Array<{ from: number; value: string }> {
  const fragments: Array<{ from: number; value: string }> = []
  const seenLines = new Set<number>()
  for (const intersection of visibleIntersections(range, visible)) {
    let line = state.doc.lineAt(intersection.from)
    while (line.from < intersection.to) {
      if (!seenLines.has(line.number)) {
        seenLines.add(line.number)
        fragments.push(linePrefixFragment(state, range, line.from, 5))
      }
      if (line.to >= state.doc.length) break
      line = state.doc.line(line.number + 1)
    }
  }
  return fragments
}

function createPreviewSourceIndex(editorSource: string, rawSource?: string) {
  if (!rawSource || rawSource === editorSource) {
    return createMarkdownSourceIndex(editorSource)
  }
  if (rawSource.replace(/\r\n/g, '\n') !== editorSource) {
    return createMarkdownSourceIndex(editorSource)
  }

  const editorToRaw = new Array<number>(editorSource.length + 1)
  let editorOffset = 0
  let rawOffset = 0
  while (rawOffset < rawSource.length) {
    editorToRaw[editorOffset] = rawOffset
    if (rawSource.startsWith('\r\n', rawOffset)) {
      rawOffset += 2
      editorOffset += 1
    } else {
      rawOffset += 1
      editorOffset += 1
    }
  }
  editorToRaw[editorOffset] = rawOffset
  const rawIndex = createMarkdownSourceIndex(rawSource)

  return {
    byteOffset: (offset: number) => rawIndex.byteOffset(
      editorToRaw[Math.max(0, Math.min(editorOffset, offset))],
    ),
  }
}

function sourceContextFor(doc: Text, rawSource?: string): PreviewSourceContext {
  let byRawSource = sourceContextCache.get(doc)
  if (!byRawSource) {
    byRawSource = new Map()
    sourceContextCache.set(doc, byRawSource)
  }
  let sourceContext = byRawSource.get(rawSource)
  if (!sourceContext) {
    const editorSource = doc.toString()
    sourceContext = {
      mathRanges: indexMathRanges(editorSource),
      sourceIndex: createPreviewSourceIndex(editorSource, rawSource),
    }
    byRawSource.set(rawSource, sourceContext)
  }
  return sourceContext
}

function createPreviewDocumentContext(
  state: EditorState,
  options: LivePreviewOptions,
): PreviewDocumentContext {
  return {
    ...sourceContextFor(state.doc, options.source),
    resolvedSpans: buildUniqueResolvedSpanMap(options.links || []),
  }
}

function linkLabel(source: string, kind: 'markdown' | 'wiki'): string {
  if (kind === 'markdown') return /^\[([^\]]*)\]/.exec(source)?.[1] || source
  const body = source.slice(2, -2)
  return (body.includes('|') ? body.slice(body.indexOf('|') + 1) : body).trim() || body.trim()
}

function markdownLinkTarget(source: string): string | undefined {
  const match = /\]\(([^\s)]+)(?:\s+[^)]*)?\)$/.exec(source)
  return match?.[1]
}

function isInternalNavigationSource(source: string, kind: 'markdown' | 'wiki'): boolean {
  const target = kind === 'markdown'
    ? markdownLinkTarget(source)
    : source.slice(2, -2).split('|', 1)[0].split('#', 1)[0].trim()
  if (!target || /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(target)) return false
  return !attachmentExtension.test(target.split(/[?#]/, 1)[0])
}

class TaskMarkerWidget extends WidgetType {
  constructor(private readonly checked: boolean) {
    super()
  }

  eq(other: TaskMarkerWidget): boolean {
    return this.checked === other.checked
  }

  toDOM(): HTMLElement {
    const input = document.createElement('input')
    input.type = 'checkbox'
    input.checked = this.checked
    input.disabled = true
    input.className = 'dn-live-preview-task'
    input.setAttribute('aria-label', this.checked ? 'Completed task' : 'Incomplete task')
    return input
  }

  ignoreEvent(): boolean {
    return true
  }
}

class NavigationWidget extends WidgetType {
  constructor(
    private readonly label: string,
    private readonly noteId: string,
    private readonly onNavigate: (noteId: string) => void,
  ) {
    super()
  }

  eq(other: NavigationWidget): boolean {
    return this.label === other.label
      && this.noteId === other.noteId
      && this.onNavigate === other.onNavigate
  }

  toDOM(): HTMLElement {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'dn-live-preview-link'
    button.textContent = this.label
    button.setAttribute('aria-label', this.label)
    button.addEventListener('click', () => this.onNavigate(this.noteId))
    return button
  }
}

function resolvedLinkFor(
  state: EditorState,
  range: SourceRange,
  kind: 'markdown' | 'wiki',
  options: LivePreviewOptions,
  resolvedSpans: Map<string, VaultLink>,
  sourceIndex: Pick<ReturnType<typeof createMarkdownSourceIndex>, 'byteOffset'>,
): VaultLink | undefined {
  if (!options.onNavigate || resolvedSpans.size === 0) return undefined
  const sourceStart = sourceIndex.byteOffset(range.from)
  const sourceEnd = sourceIndex.byteOffset(range.to)
  const link = resolvedSpans.get(vaultLinkSpanKey(sourceStart, sourceEnd))
  if (!link?.target_note_id || !isInternalNavigationSource(sourceText(state, range), kind)) {
    return undefined
  }
  return link
}

function createRecords(
  state: EditorState,
  ranges: readonly SourceRange[],
  options: LivePreviewOptions,
  context: PreviewDocumentContext,
): PreviewDecorationRecord[] {
  const visible = visibleRanges(state, ranges)
  if (visible.length === 0) return []

  const bounded = scannerRanges(state, visible)
  const rawWikiRanges = collectMatches(state.doc, bounded, /\[\[[^\]\r\n]{1,2048}\]\]/gu)
  const rawFootnoteRanges = collectMatches(state.doc, bounded, /\[\^[^\]\r\n]{1,256}\]/gu)
  const rawMathRanges = indexedIntersections(context.mathRanges, visible)
  const parserRanges: Array<{ kind: MarkdownConstructKind; range: SourceRange }> = []
  const exclusions: SourceRange[] = []
  const seenParserRanges = new Set<string>()
  const tree = syntaxTree(state)

  for (const range of visible) {
    tree.iterate({
      from: range.from,
      to: range.to,
      enter: ({ from, name, to }) => {
        const kind = /^ATXHeading[1-6]$/.test(name) || /^SetextHeading[1-6]$/.test(name)
          ? 'heading'
          : parserKinds[name]
        if (!kind || !isVisible({ from, to }, visible)) return
        const key = `${kind}:${from}:${to}`
        if (seenParserRanges.has(key)) return
        seenParserRanges.add(key)
        parserRanges.push({ kind, range: { from, to } })
        const parserRange = { from, to }
        const linkArtifact = kind === 'link'
          && (containedBy(parserRange, rawWikiRanges)
            || to - from <= 260
              && /^\[\^[^\]]+\]$/u.test(state.doc.sliceString(from, to)))
        if (
          kind === 'inline-code'
          || kind === 'fenced-code'
          || kind === 'link' && !linkArtifact
        ) {
          exclusions.push({ from, to })
        }
      },
    })
  }

  const mergedExclusions = mergeRanges(exclusions)
  const wikiRanges = rawWikiRanges.filter((range) => !overlapsSorted(range, mergedExclusions))
  const footnoteRanges = rawFootnoteRanges.filter((range) => !overlapsSorted(range, mergedExclusions))
  const mathRanges = rawMathRanges.filter((range) => !overlapsSorted(range, mergedExclusions))
  const tagRanges = collectMatches(
    state.doc,
    bounded,
    /(?:^|[\s([{])(#[\p{Letter}\p{Number}_/-]{1,256})/gmu,
  ).map((range) => {
    const tag = /#[\p{Letter}\p{Number}_/-]{1,256}/u.exec(
      state.doc.sliceString(range.from, range.to),
    )?.[0]
    return tag ? { from: range.to - tag.length, to: range.to } : range
  }).filter((range) => !overlapsSorted(range, mergedExclusions))

  const records: PreviewDecorationRecord[] = []
  const pushRecord = (
    kind: string,
    range: SourceRange,
    decoration: Decoration,
    atomic: boolean,
  ) => records.push({ kind, from: range.from, to: range.to, decoration, atomic })
  const add = (
    kind: string,
    range: SourceRange,
    decoration: Decoration,
    atomic = false,
  ) => {
    try {
      for (const intersection of visibleIntersections(range, visible)) {
        pushRecord(kind, intersection, decoration, atomic)
      }
    } catch {
      // Decoration failures must not hide unrelated visible source.
    }
  }
  const replace = (
    kind: string,
    range: SourceRange,
    decoration: Decoration,
    atomic = false,
  ) => {
    if (!rangeIsSingleLine(state, range) || !isFullyVisible(range, visible)) return
    pushRecord(kind, range, decoration, atomic)
  }

  for (const { kind, range } of parserRanges) {
    try {
      if (selectionIntersects(state, range)) continue
      if (kind === 'heading') {
        const prefix = linePrefixFragment(state, range, range.from).value
        const marker = /^ {0,3}#{1,6}[ \t]+/.exec(prefix)?.[0]
        if (marker) {
          replace('heading-mark', {
            from: range.from,
            to: range.from + marker.length,
          }, Decoration.replace({}))
        } else if (range.to - range.from <= constructReadLimit) {
          const value = sourceText(state, range)
          const underlines = [...value.matchAll(/^ {0,3}[=-]+[ \t]*$/gmu)]
          for (const underline of underlines) {
            replace('heading-mark', {
              from: range.from + (underline.index || 0),
              to: range.from + (underline.index || 0) + underline[0].length,
            }, Decoration.replace({}))
          }
        }
        add('heading-content', range, Decoration.mark({ class: 'dn-live-preview-heading' }))
      } else if (kind === 'emphasis' || kind === 'strong' || kind === 'strikethrough') {
        const marker = pairedMarker(
          state,
          range,
          kind === 'emphasis' ? /^[_*]/u
            : kind === 'strong' ? /^(?:\*\*|__)/u
              : /^~~/u,
        )
        if (!marker) continue
        replace(`${kind}-mark`, { from: range.from, to: range.from + marker.length }, Decoration.replace({}))
        replace(`${kind}-mark`, { from: range.to - marker.length, to: range.to }, Decoration.replace({}))
        add(`${kind}-content`, range, Decoration.mark({ class: `dn-live-preview-${kind}` }))
      } else if (kind === 'inline-code') {
        const marker = pairedMarker(state, range, /^`+/u)
        if (!marker) continue
        replace('inline-code-mark', { from: range.from, to: range.from + marker.length }, Decoration.replace({}))
        replace('inline-code-mark', { from: range.to - marker.length, to: range.to }, Decoration.replace({}))
        add('inline-code-content', range, Decoration.mark({ class: 'dn-live-preview-code' }))
      } else if (kind === 'fenced-code') {
        const fragments = [
          linePrefixFragment(state, range, range.from),
          linePrefixFragment(state, range, range.to - 1),
        ].filter((fragment, index, all) =>
          all.findIndex((candidate) => candidate.from === fragment.from) === index,
        )
        for (const fragment of fragments) {
          const fence = /^( {0,3}(?:`{3,}|~{3,}))/u.exec(fragment.value)
          if (!fence) continue
          replace('fenced-code-mark', {
            from: fragment.from,
            to: fragment.from + fence[1].length,
          }, Decoration.replace({}))
        }
        add('fenced-code-content', range, Decoration.mark({ class: 'dn-live-preview-code' }))
      } else if (kind === 'link') {
        if (containedBy(range, wikiRanges) || containedBy(range, footnoteRanges)) continue
        const canReadLink = range.to - range.from <= constructReadLimit
        const value = canReadLink ? sourceText(state, range) : ''
        const link = canReadLink && isFullyVisible(range, visible)
          ? resolvedLinkFor(
            state,
            range,
            'markdown',
            options,
            context.resolvedSpans,
            context.sourceIndex,
          )
          : undefined
        if (link && options.onNavigate) {
          replace('markdown-link', range, Decoration.replace({
            widget: new NavigationWidget(linkLabel(value, 'markdown'), link.target_note_id!, options.onNavigate),
          }), true)
          continue
        }
        add('markdown-link', range, Decoration.mark({ class: 'dn-live-preview-link-mark' }))
        const closingBracket = value.indexOf(']')
        if (closingBracket >= 0) {
          replace('markdown-link-mark', { from: range.from, to: range.from + 1 }, Decoration.replace({}))
          replace('markdown-link-mark', { from: range.from + closingBracket, to: range.to }, Decoration.replace({}))
        }
      } else if (kind === 'task-marker') {
        const value = linePrefixFragment(state, range, range.from, 3).value
        replace('task-marker', range, Decoration.replace({
          widget: new TaskMarkerWidget(/^\[x\]/i.test(value)),
        }))
      } else if (kind === 'blockquote') {
        for (const fragment of visibleLinePrefixFragments(state, range, visible)) {
          const marker = /^ {0,3}>[ \t]?/u.exec(fragment.value)?.[0]
          if (!marker) continue
          replace('blockquote-mark', {
            from: fragment.from,
            to: fragment.from + marker.length,
          }, Decoration.replace({}))
        }
        add('blockquote-content', range, Decoration.mark({ class: 'dn-live-preview-quote' }))
      } else if (kind === 'horizontal-rule') {
        add('horizontal-rule', range, Decoration.mark({ class: 'dn-live-preview-rule' }))
      } else if (kind === 'list-marker') {
        const value = linePrefixFragment(state, range, range.from, 1).value
        const listKind = /^\d/.test(value) ? 'ordered-list-mark' : 'unordered-list-mark'
        add(listKind, range, Decoration.mark({ class: 'dn-live-preview-list-marker' }))
      }
    } catch {
      // Unsupported parser nodes remain source-visible, independently of peers.
    }
  }

  for (const range of wikiRanges) {
    try {
      if (selectionIntersects(state, range)) continue
      const value = sourceText(state, range)
      const link = isFullyVisible(range, visible)
        ? resolvedLinkFor(
          state,
          range,
          'wiki',
          options,
          context.resolvedSpans,
          context.sourceIndex,
        )
        : undefined
      if (link && options.onNavigate) {
        replace('wiki-link', range, Decoration.replace({
          widget: new NavigationWidget(linkLabel(value, 'wiki'), link.target_note_id!, options.onNavigate),
        }), true)
        continue
      }
      add('wiki-link', range, Decoration.mark({ class: 'dn-live-preview-link-mark' }))
      replace('wiki-link-mark', { from: range.from, to: range.from + 2 }, Decoration.replace({}))
      replace('wiki-link-mark', { from: range.to - 2, to: range.to }, Decoration.replace({}))
    } catch {
      // Keep malformed wiki syntax inspectable.
    }
  }

  for (const range of tagRanges) {
    try {
      if (!selectionIntersects(state, range)) {
        add('tag', range, Decoration.mark({ class: 'dn-live-preview-tag' }))
      }
    } catch {
      // Omit only the failed scanner construct.
    }
  }
  for (const range of footnoteRanges) {
    try {
      if (!selectionIntersects(state, range)) {
        add('footnote-mark', range, Decoration.mark({ class: 'dn-live-preview-footnote' }))
      }
    } catch {
      // Omit only the failed scanner construct.
    }
  }
  for (const range of mathRanges) {
    try {
      if (!selectionIntersects(state, range)) {
        add('math-mark', range, Decoration.mark({ class: 'dn-live-preview-math' }))
      }
    } catch {
      // Omit only the failed scanner construct.
    }
  }

  return records.sort((left, right) => left.from - right.from
    || left.decoration.startSide - right.decoration.startSide
    || left.to - right.to)
}

export function buildLivePreviewDecorationRecords(
  state: EditorState,
  ranges: readonly SourceRange[],
  options: LivePreviewOptions = {},
): PreviewDecorationRecord[] {
  return createRecords(
    state,
    ranges,
    options,
    createPreviewDocumentContext(state, options),
  )
}

function decorationSets(
  state: EditorState,
  ranges: readonly SourceRange[],
  options: LivePreviewOptions,
  context: PreviewDocumentContext,
): { decorations: DecorationSet; atomicRanges: DecorationSet } {
  const records = createRecords(state, ranges, options, context)
  return {
    decorations: Decoration.set(
      records.map((record) => record.decoration.range(record.from, record.to)),
      true,
    ),
    atomicRanges: Decoration.set(
      records.filter((record) => record.atomic)
        .map((record) => record.decoration.range(record.from, record.to)),
      true,
    ),
  }
}

export function buildLivePreviewDecorations(view: EditorView): DecorationSet {
  const options = {}
  return decorationSets(
    view.state,
    view.visibleRanges,
    options,
    createPreviewDocumentContext(view.state, options),
  ).decorations
}

export function livePreviewExtension(options: LivePreviewOptions): Extension {
  const plugin = ViewPlugin.fromClass(class {
    decorations: DecorationSet
    atomicRanges: DecorationSet
    context: PreviewDocumentContext

    constructor(view: EditorView) {
      this.context = createPreviewDocumentContext(view.state, options)
      const sets = decorationSets(
        view.state,
        view.visibleRanges,
        options,
        this.context,
      )
      this.decorations = sets.decorations
      this.atomicRanges = sets.atomicRanges
    }

    update(update: { docChanged: boolean; selectionSet: boolean; viewportChanged: boolean; view: EditorView }) {
      if (update.docChanged || update.selectionSet || update.viewportChanged) {
        if (update.docChanged) {
          this.context = createPreviewDocumentContext(update.view.state, options)
        }
        const sets = decorationSets(
          update.view.state,
          update.view.visibleRanges,
          options,
          this.context,
        )
        this.decorations = sets.decorations
        this.atomicRanges = sets.atomicRanges
      }
    }
  }, {
    decorations: (plugin) => plugin.decorations,
  })

  return [
    plugin,
    EditorView.atomicRanges.of(
      (view) => view.plugin(plugin)?.atomicRanges || Decoration.none,
    ),
  ]
}

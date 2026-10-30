/**
 * citations.ts — Pure regex splitter for citation markers in chat assistant text.
 *
 * Two marker shapes are supported:
 *   [mcp:N]           — MCP tool-call reference (N = 1-based integer per turn)
 *   [source:ID]       — SurrealDB source record
 *   [note:ID]         — SurrealDB note record
 *   [insight:ID]      — SurrealDB insight record
 *
 * v0.8.0 Phase 4 Task 14 — added alongside CitationPill component.
 */

export type CitationKind = 'mcp' | 'source' | 'note' | 'insight'

export type CitationSegment =
  | { kind: 'text'; value: string }
  | { kind: CitationKind; value: string }

/**
 * Regex that matches all four citation shapes.
 * Named capture groups:
 *   - kind  — "mcp" | "source" | "note" | "insight"
 *   - ref   — the identifier (integer string for mcp, alphanumeric ID for others)
 *
 * @example
 *   "[mcp:1]"       → kind="mcp",     ref="1"
 *   "[source:abc1]" → kind="source",  ref="abc1"
 *   "[note:xyz]"    → kind="note",    ref="xyz"
 *   "[insight:q9r]" → kind="insight", ref="q9r"
 */
export const CITATION_RE = /\[(mcp|source|note|insight):([A-Za-z0-9_-]+)\]/g

/**
 * Split `text` into an alternating sequence of plain-text and citation segments.
 *
 * The returned array preserves document order. Empty text segments are omitted
 * (e.g. if two citation markers appear back-to-back there is no empty text
 * node between them).
 *
 * @param text - Raw assistant message text, possibly containing citation markers.
 * @returns Array of segments ready for rendering.
 *
 * @example
 *   splitCitations("Hello [mcp:1] world")
 *   // → [{ kind:"text", value:"Hello " }, { kind:"mcp", value:"1" }, { kind:"text", value:" world" }]
 */
export function splitCitations(text: string): CitationSegment[] {
  if (!text) return []

  const segments: CitationSegment[] = []
  let lastIndex = 0

  // Reset lastIndex before each call since CITATION_RE is module-level.
  CITATION_RE.lastIndex = 0

  let match: RegExpExecArray | null
  while ((match = CITATION_RE.exec(text)) !== null) {
    // Text before this citation
    if (match.index > lastIndex) {
      segments.push({ kind: 'text', value: text.slice(lastIndex, match.index) })
    }

    const kind = match[1] as CitationKind
    const ref = match[2]
    segments.push({ kind, value: ref })

    lastIndex = CITATION_RE.lastIndex
  }

  // Remaining text after the last citation (or the whole string if none matched)
  if (lastIndex < text.length) {
    segments.push({ kind: 'text', value: text.slice(lastIndex) })
  }

  return segments
}

/** Href prefix of the markdown links {@link linkifyCitations} emits. */
export const CITATION_HREF_PREFIX = '#dn-cite-'

export interface LinkedCitation {
  kind: CitationKind
  value: string
  /**
   * 1-based, in order of first appearance and shared by every occurrence of the
   * same source/note/insight. `null` for MCP tool calls, which keep their own
   * per-turn index as the label.
   */
  number: number | null
  /** Text between the previous marker (or the start) and this one: the claim being cited. */
  precedingText: string
}

// v0.8.130 — Fenced blocks and inline code alternate with prose when split on this
// pattern (the capture group keeps the code chunks at odd indexes). A fence that
// has not closed yet, as while the answer is still streaming, runs to the end.
const CODE_SPAN_RE = /(```[\s\S]*?```|~~~[\s\S]*?~~~|```[\s\S]*$|~~~[\s\S]*$|`[^`\n]*`)/

/**
 * v0.8.130 — Turn citation markers into ordinary markdown links so the whole answer can
 * go through a single markdown pass and each citation stays inside the sentence
 * it supports. Splitting on markers and rendering each piece separately made
 * every piece its own block, which pushed each pill onto its own line.
 *
 * Markers inside code spans and fenced blocks are left as written by this
 * function. (The older compact-reference conversion that runs on the result is
 * not code-aware and is unchanged.)
 */
export function linkifyCitations(text: string): { markdown: string; citations: LinkedCitation[] } {
  if (!text) return { markdown: '', citations: [] }

  const citations: LinkedCitation[] = []
  const numbers = new Map<string, number>()
  let markdown = ''
  let context = ''

  text.split(CODE_SPAN_RE).forEach((chunk, index) => {
    if (index % 2 === 1) {
      markdown += chunk
      context += chunk
      return
    }

    // A fresh regex per chunk keeps the module-level CITATION_RE untouched.
    const re = new RegExp(CITATION_RE.source, 'g')
    let last = 0
    for (let match = re.exec(chunk); match; match = re.exec(chunk)) {
      const before = chunk.slice(last, match.index)
      markdown += before
      context += before

      const kind = match[1] as CitationKind
      const value = match[2]
      let number: number | null = null
      if (kind !== 'mcp') {
        const key = `${kind}:${value}`
        number = numbers.get(key) ?? numbers.size + 1
        numbers.set(key, number)
      }

      markdown += `[${number ?? `${kind} ${value}`}](${CITATION_HREF_PREFIX}${citations.length})`
      citations.push({ kind, value, number, precedingText: context })
      context = ''
      last = match.index + match[0].length
    }

    const rest = chunk.slice(last)
    markdown += rest
    context += rest
  })

  return { markdown, citations }
}

/** Index into the `citations` list for a link emitted by {@link linkifyCitations}, else null. */
export function parseCitationHref(href: string | null | undefined): number | null {
  if (!href || !href.startsWith(CITATION_HREF_PREFIX)) return null
  const raw = href.slice(CITATION_HREF_PREFIX.length)
  return /^\d+$/.test(raw) ? Number(raw) : null
}

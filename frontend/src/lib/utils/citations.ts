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

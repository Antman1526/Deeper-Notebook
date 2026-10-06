// v0.8.130 — every notebook is bound in one of a few cloth colours, chosen from its id
// so the same notebook always wears the same cover, on every device, with nothing stored.
// The colours themselves live in workspace.css ([data-dn-cover='…']).
export const NOTEBOOK_COVER_TONES = ['ink', 'forest', 'oxblood', 'ochre', 'slate', 'plum'] as const

export type NotebookCoverTone = (typeof NOTEBOOK_COVER_TONES)[number]

export function notebookCoverTone(notebookId: string): NotebookCoverTone {
  // FNV-1a: small, stable across engines, and spreads sequential ids well.
  let hash = 0x811c9dc5
  for (let index = 0; index < notebookId.length; index += 1) {
    hash ^= notebookId.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return NOTEBOOK_COVER_TONES[(hash >>> 0) % NOTEBOOK_COVER_TONES.length]
}

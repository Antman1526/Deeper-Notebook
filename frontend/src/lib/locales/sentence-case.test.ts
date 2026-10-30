// v0.8.130 — Phase 4a of the 2026-09-30 UI audit: en-US copy is sentence case
// ("New notebook", "Sign in"), like the rest of the premium pass. Title Case is kept
// only for proper nouns and product names. Other locales follow their own rules
// (German capitalizes nouns), so only en-US is checked.

import { describe, expect, it } from 'vitest'

import { enUS } from './en-US'

// Words (or phrases) that keep their capitals anywhere in a string.
const PROPER_NOUNS = [
  // Multi-word names first: each name is removed in order, so 'Google' must not split them.
  'Google Cloud Console', 'Google Cloud', 'Google Drive', 'OAuth', 'WebVTT', 'Canvas',
  'Deeper Notebook', 'Evidence Studio', 'Research Core', 'Study Workbench',
  'ExamLab', 'Cornell Notes', 'Course Pack', 'Episode Lab', 'Gemini-Forward', 'Luminous Folio',
  'Obsidian', 'Docker', 'Gmail', 'Google', 'GitHub', 'YouTube', 'Ollama', 'OpenAI', 'Anthropic',
  'Anki', 'Tavily', 'Markdown', 'SurrealDB', 'Apple', 'Silicon', 'Metal', 'FlashAttention', 'Mac',
  'Windows', 'Linux', 'Chrome', 'Zotero', 'Notion', 'Logseq', 'Paperless', 'English',
  'Chinese', 'Spanish', 'French', 'German', 'Italian', 'Japanese', 'Portuguese', 'Russian',
  'Turkish', 'Polish', 'Catalan', 'Bengali', 'Traditional', 'Simplified', 'FSRS', 'Whisper',
  'Osaurus', 'LangGraph', 'Gemini',
  // Destination and panel names, as in the navigation.
  'Studio',
]

function words(value: string): string[] {
  return value.split(/\s+/).filter(Boolean)
}

/** Words after the first that are capitalized without a reason. */
function titleCaseWords(value: string): string[] {
  const text = PROPER_NOUNS.reduce((acc, noun) => acc.split(noun).join(''), value)
  const list = words(text)
  const offenders: string[] = []
  for (let index = 1; index < list.length; index += 1) {
    const word = list[index]
    const previous = list[index - 1]
    // A new sentence, a label after a colon, or a quoted/bracketed start.
    if (/[.!?:—]$/.test(previous) || /^["“'(«{]/.test(word)) continue
    // Acronyms, versions and identifiers (API, GPU, v2, Q8_0, iOS).
    // Two or more capitals, so "APIs" passes and "As" does not.
    if (/^[A-Z0-9][A-Z0-9_./+-]+s?[.,:;!?)]*$/.test(word) || /^[A-Z][.,:;!?)]*$/.test(word) || /\d/.test(word)) continue
    // Keyboard shortcuts (Cmd/Ctrl+Enter).
    if (/[+/]/.test(word)) continue
    if (/^\{\{/.test(word)) continue
    if (/^[A-Z][a-z]/.test(word)) offenders.push(word)
  }
  return offenders
}

function collect(node: unknown, path: string[], out: Array<[string, string]>) {
  if (typeof node === 'string') {
    out.push([path.join('.'), node])
    return
  }
  if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node)) collect(value, [...path, key], out)
  }
}

describe('en-US sentence case', () => {
  it('keeps capitals only for the first word, proper nouns and acronyms', () => {
    const entries: Array<[string, string]> = []
    collect(enUS, [], entries)
    const offenders = entries
      .filter(([, value]) => words(value).length >= 2 && words(value).length <= 12)
      .map(([key, value]) => [key, value, titleCaseWords(value)] as const)
      .filter(([, , found]) => found.length > 0)
      .map(([key, value]) => `${key}: ${value}`)
    expect(offenders).toEqual([])
  })

  it('leaves proper nouns, acronyms and new sentences alone', () => {
    expect(titleCaseWords('Open in Deeper Notebook')).toEqual([])
    expect(titleCaseWords('Connect your Gmail account')).toEqual([])
    expect(titleCaseWords('Configure the API key')).toEqual([])
    expect(titleCaseWords('Saved. Try again later')).toEqual([])
    expect(titleCaseWords('Create New Notebook')).toEqual(['New', 'Notebook'])
    expect(titleCaseWords('Save Current As')).toEqual(['Current', 'As'])
    expect(titleCaseWords('Configure your APIs')).toEqual([])
  })
})

// v0.8.130 — auto-registered local credentials are stored with English names; the
// label is translated at display time while the stored name stays untouched.
import { describe, expect, it } from 'vitest'
import { enUS } from '@/lib/locales/en-US'
import { localCredentialLabel } from './local-credential-label'

type Tree = Record<string, unknown>

function lookup(key: string): string {
  const value = key.split('.').reduce<unknown>((node, part) => (node as Tree | undefined)?.[part], enUS as Tree)
  return typeof value === 'string' ? value : key
}

/** en-US t(): resolves the real locale string and fills {{placeholders}}. */
const tEnglish = (key: string, vars?: Record<string, unknown>) =>
  lookup(key).replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(vars?.[name] ?? ''))

/** A stand-in for a non-English locale, to prove the label goes through t(). */
const tGerman = (key: string, vars?: Record<string, unknown>) => {
  const table: Record<string, string> = {
    'models.localCredential.named': '{{name}} (lokal)',
    'models.localCredential.memory': 'Gedächtnis',
  }
  return (table[key] ?? key).replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(vars?.[name] ?? ''))
}

const STORED_NAMES = [
  'Memory (local)',
  'Whisper (local)',
  'Piper (local)',
  'Ollama (local)',
  'LM Studio (local)',
  'MLX (local)',
  'llama.cpp (local)',
]

describe('localCredentialLabel', () => {
  it.each(STORED_NAMES)('en-US renders the stored name unchanged: %s', (stored) => {
    expect(localCredentialLabel(stored, tEnglish)).toBe(stored)
  })

  it('translates the "local" word for a known name', () => {
    expect(localCredentialLabel('Whisper (local)', tGerman)).toBe('Whisper (lokal)')
    expect(localCredentialLabel('Piper (local)', tGerman)).toBe('Piper (lokal)')
    expect(localCredentialLabel('Ollama (local)', tGerman)).toBe('Ollama (lokal)')
    expect(localCredentialLabel('LM Studio (local)', tGerman)).toBe('LM Studio (lokal)')
    expect(localCredentialLabel('MLX (local)', tGerman)).toBe('MLX (lokal)')
    expect(localCredentialLabel('llama.cpp (local)', tGerman)).toBe('llama.cpp (lokal)')
  })

  it('translates "Memory" as well as "local"', () => {
    expect(localCredentialLabel('Memory (local)', tGerman)).toBe('Gedächtnis (lokal)')
  })

  it('returns an unknown name unchanged', () => {
    expect(localCredentialLabel('My OpenAI key', tGerman)).toBe('My OpenAI key')
  })

  it('returns a user name that merely ends in "(local)" unchanged', () => {
    expect(localCredentialLabel('Home server (local)', tGerman)).toBe('Home server (local)')
    expect(localCredentialLabel('Whisper (local) 2', tGerman)).toBe('Whisper (local) 2')
  })

  it('matches case-sensitively', () => {
    expect(localCredentialLabel('whisper (local)', tGerman)).toBe('whisper (local)')
    expect(localCredentialLabel('OLLAMA (LOCAL)', tGerman)).toBe('OLLAMA (LOCAL)')
  })

  it('does not treat inherited object keys as known names', () => {
    expect(localCredentialLabel('constructor', tGerman)).toBe('constructor')
    expect(localCredentialLabel('toString', tGerman)).toBe('toString')
  })
})

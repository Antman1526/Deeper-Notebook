// v0.8.130 — Markup parity across locales.
//
// Sentences with an inline link, key or code value are one translation with tags
// ("Tip: hit <key/> from anywhere…"), rendered by components/common/RichText.tsx, so
// each language can place the element where its grammar needs it. A translation that
// drops or renames a tag would silently lose the link or the value; this requires every
// locale string to carry exactly the tags its en-US counterpart carries.

import { describe, expect, it } from 'vitest'
import { resources } from './index'
import { enUS } from './en-US'

type Tree = Record<string, unknown>

function flatten(obj: Tree, prefix = '', out: Record<string, string> = {}): Record<string, string> {
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') out[path] = value
    else if (typeof value === 'object' && value !== null && !Array.isArray(value)) flatten(value as Tree, path, out)
  }
  return out
}

function tags(text: string): string[] {
  return [...(text.match(/<\/?[a-zA-Z][\w-]*\s*\/?>/g) ?? [])].sort()
}

describe('Locale markup parity', () => {
  const en = flatten(enUS as Tree)
  const tagged = Object.entries(en).filter(([, text]) => tags(text).length > 0)

  it('en-US has tagged sentences to compare against', () => {
    expect(tagged.length).toBeGreaterThanOrEqual(10)
  })

  it.each(Object.entries(resources).filter(([code]) => code !== 'en-US'))('%s keeps every markup tag', (_code, resource) => {
    const locale = flatten(resource.translation as Tree)
    const drift = tagged
      .filter(([key, text]) => key in locale && tags(locale[key]).join() !== tags(text).join())
      .map(([key]) => key)
    expect(drift).toEqual([])
  })
})

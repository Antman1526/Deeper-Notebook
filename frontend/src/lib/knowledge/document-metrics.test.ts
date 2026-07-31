import { describe, expect, it } from 'vitest'

import { documentMetrics } from './document-metrics'

describe('documentMetrics', () => {
  it.each([
    ['hello world', 2, 11, 10],
    ['你好世界', 2, 4, 4],
    ['cafe\u0301 ☕', 1, 7, 6],
    ['', 0, 0, 0],
  ])('counts %s deterministically', (text, words, characters, noWhitespace) => {
    expect(documentMetrics(text)).toMatchObject({
      words,
      characters,
      charactersWithoutWhitespace: noWhitespace,
      readingMinutes: words === 0 ? 0 : 1,
    })
  })

  it('counts Unicode code points rather than UTF-16 units', () => {
    expect(documentMetrics('🧠').characters).toBe(1)
  })

  it('uses an injected segmenter for deterministic caller-provided counts', () => {
    const segmenter = {
      segment: () => [
        { segment: 'alpha', isWordLike: true },
        { segment: ' ', isWordLike: false },
        { segment: 'beta', isWordLike: true },
      ],
    }

    expect(documentMetrics('ignored', segmenter)).toMatchObject({
      words: 2,
      characters: 7,
      charactersWithoutWhitespace: 7,
      readingMinutes: 1,
    })
  })

  it('rounds non-empty reading time up to one minute per 200 words', () => {
    expect(documentMetrics(Array(201).fill('word').join(' ')).readingMinutes)
      .toBe(2)
  })
})

export interface DocumentMetrics {
  words: number
  characters: number
  charactersWithoutWhitespace: number
  readingMinutes: number
}

export interface WordSegment {
  isWordLike?: boolean
}

export interface WordSegmenter {
  segment(text: string): Iterable<WordSegment>
}

function fallbackWordCount(text: string): number {
  // Offline fallback: preserve ordinary Letter/Number/Mark runs as one token,
  // while approximating an unspaced Han run as two code points per word.
  return (text.match(/[\p{Letter}\p{Number}\p{Mark}]+/gu) ?? []).reduce(
    (words, token) => words + (/^\p{Script=Han}+$/u.test(token)
      ? Math.ceil(Array.from(token).length / 2)
      : 1),
    0,
  )
}

function runtimeWordSegmenter(): WordSegmenter | null {
  if (typeof Intl.Segmenter !== 'function') return null
  return new Intl.Segmenter('und', { granularity: 'word' })
}

export function documentMetrics(
  text: string,
  segmenter: WordSegmenter | null | undefined = runtimeWordSegmenter(),
): DocumentMetrics {
  const characters = Array.from(text)
  const words = segmenter
    ? Array.from(segmenter.segment(text)).filter((segment) => segment.isWordLike).length
    : fallbackWordCount(text)

  return {
    words,
    characters: characters.length,
    charactersWithoutWhitespace: characters.filter(
      (character) => !/\p{White_Space}/u.test(character),
    ).length,
    readingMinutes: words === 0 ? 0 : Math.ceil(words / 200),
  }
}

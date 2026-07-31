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
  return (text.match(/[\p{Letter}\p{Number}\p{Mark}]+/gu) ?? []).length
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
    charactersWithoutWhitespace: characters.filter((character) => !/\s/u.test(character)).length,
    readingMinutes: words === 0 ? 0 : Math.ceil(words / 200),
  }
}

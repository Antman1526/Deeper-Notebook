import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

// v0.8.130 — on a phone a source card puts its cover in a 6rem column beside the
// details. A source with no cover image draws its title and status INSIDE that cover,
// so they were squeezed into 6rem: "Determi / nistic / source", "unavaila / ble". A
// card whose cover is the text fallback takes the full width at that size instead.
const css = fs.readFileSync(path.resolve(__dirname, 'source-gallery.css'), 'utf8')

describe('source gallery on a phone', () => {
  it('gives a card without a cover image the full width', () => {
    const narrow = css.slice(css.indexOf('@container source-gallery (max-width: 34rem)'))
    const block = narrow.slice(0, narrow.indexOf('\n}\n') + 3)
    expect(block).toMatch(
      /\.dn-source-cover--card:has\(\.dn-source-cover__visual--fallback\)\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/,
    )
  })
})

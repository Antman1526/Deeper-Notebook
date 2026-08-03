import { describe, expect, it } from 'vitest'

import { redactAbsolutePaths } from './safe-text'

describe('redactAbsolutePaths', () => {
  it('preserves ordinary prose, relative locators, ratios, and HTTPS URLs', () => {
    const value = 'Compare pros/cons and/or 1/2 in notes/plan.md at https://example.com/Users/owner/guide.'

    expect(redactAbsolutePaths(value)).toBe(value)
  })

  it('redacts embedded POSIX, Windows, UNC, and file absolute paths', () => {
    expect(redactAbsolutePaths('Imported from /Users/Antman/Secret/note.md')).toBe('Imported from [path redacted]')
    expect(redactAbsolutePaths('Read /etc/passwd')).toBe('Read [path redacted]')
    expect(redactAbsolutePaths('Read C:\\Users\\Antman\\Secret\\note.md')).toBe('Read [path redacted]')
    expect(redactAbsolutePaths('Read \\\\server\\share\\secret.md')).toBe('Read [path redacted]')
    expect(redactAbsolutePaths('Read file:///private/secret.md')).toBe('Read [path redacted]')
  })
})

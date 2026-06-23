import { describe, expect, it } from 'vitest'

import { filesFromInput, formatBytes, getOversizedFiles } from './SourceTypeStep'

describe('SourceTypeStep file helpers', () => {
  it('normalizes a single selected file', () => {
    const file = new File(['small'], 'small.txt', { type: 'text/plain' })

    expect(filesFromInput(file)).toEqual([file])
  })

  it('detects files larger than the active upload cap', () => {
    const small = new File(['small'], 'small.txt', { type: 'text/plain' })
    const large = new File(['large-file'], 'large.txt', { type: 'text/plain' })

    expect(getOversizedFiles([small, large] as unknown as FileList, 5).map(file => file.name)).toEqual([
      'large.txt',
    ])
  })

  it('formats byte limits for user-facing upload messages', () => {
    expect(formatBytes(500 * 1024 * 1024)).toBe('500 MB')
    expect(formatBytes(1536 * 1024 * 1024)).toBe('1.5 GB')
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { CaptureItemRow } from './CaptureItemRow'

describe('CaptureItemRow', () => {
  it('shows a file state without claiming it was imported', () => {
    render(<CaptureItemRow item={{
      id: 'capture:one', root_path: '/Users/antman/inbox', relative_path: 'voice-note.mp3', filename: 'voice-note.mp3', extension: '.mp3', state: 'ready', sha256: null, byte_size: 2_048, modified_ns: null, reason: null,
    }} />)
    expect(screen.getByText('voice-note.mp3')).toBeInTheDocument()
    expect(screen.getByText('ready')).toBeInTheDocument()
  })
})

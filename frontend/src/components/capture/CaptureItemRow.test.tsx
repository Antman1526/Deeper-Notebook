import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { captureApi } from '@/lib/api/capture'
import { CaptureItemRow } from './CaptureItemRow'

describe('CaptureItemRow', () => {
  it('shows a file state without claiming it was imported', () => {
    render(
      <CaptureItemRow
        item={{
          id: 'capture:one',
          root_path: '/Users/antman/inbox',
          relative_path: 'voice-note.mp3',
          filename: 'voice-note.mp3',
          extension: '.mp3',
          state: 'ready',
          sha256: null,
          byte_size: 2_048,
          modified_ns: null,
          reason: null,
        }}
      />
    )
    expect(screen.getByText('voice-note.mp3')).toBeInTheDocument()
    expect(screen.getByText('ready')).toBeInTheDocument()
  })

  it('shows a local-only transcript preview and notebook suggestions', async () => {
    const route = vi.spyOn(captureApi, 'route').mockResolvedValue({
      state: 'ready',
      transcript: 'Compare the private research source.',
      notebook_suggestions: [
        {
          id: 'notebook:research',
          name: 'Private Research',
          score: 2,
          reason: 'Matched research',
        },
      ],
      approval_required: true,
      reason: null,
    })
    render(
      <CaptureItemRow
        item={{
          id: 'capture:one',
          root_path: '/Users/antman/inbox',
          relative_path: 'voice-note.mp3',
          filename: 'voice-note.mp3',
          extension: '.mp3',
          state: 'ready',
          sha256: 'a'.repeat(64),
          byte_size: 2_048,
          modified_ns: 1,
          reason: null,
        }}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Review route' }))

    await waitFor(() =>
      expect(screen.getByText('Local transcript preview')).toBeInTheDocument()
    )
    expect(
      screen.getByText('Compare the private research source.')
    ).toBeInTheDocument()
    expect(screen.getByText('Private Research')).toBeInTheDocument()
    expect(screen.getByText(/original file remains where it is/i)).toBeInTheDocument()
    expect(route).toHaveBeenCalledWith('/Users/antman/inbox/voice-note.mp3')
    route.mockRestore()
  })
})

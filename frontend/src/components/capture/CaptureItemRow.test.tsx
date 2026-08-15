import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { captureApi } from '@/lib/api/capture'
import { CaptureInbox } from './CaptureInbox'
import { CaptureItemRow } from './CaptureItemRow'

const { mockVisualSystemEnabled, mockSourceVisualsEnabled, mockCaptureItems } = vi.hoisted(() => ({
  mockVisualSystemEnabled: vi.fn(() => false),
  mockSourceVisualsEnabled: vi.fn(() => false),
  mockCaptureItems: { current: [] as Array<Record<string, unknown>> },
}))

vi.mock('@/lib/features', () => ({
  isVisualSystemV2Enabled: mockVisualSystemEnabled,
  isSourceVisualsEnabled: mockSourceVisualsEnabled,
}))
vi.mock('@/lib/hooks/use-capture', () => ({
  useCaptureRoots: () => ({ data: [] }),
  useCaptureItems: () => ({ data: mockCaptureItems.current, isLoading: false, isError: false }),
  useCaptureActions: () => ({
    addRoot: { isPending: false, mutateAsync: vi.fn() },
    scan: { isPending: false, mutateAsync: vi.fn() },
  }),
}))

describe('CaptureItemRow', () => {
  beforeEach(() => {
    mockVisualSystemEnabled.mockReturnValue(false)
    mockSourceVisualsEnabled.mockReturnValue(false)
    mockCaptureItems.current = []
  })
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

  it('renders an actionless compact cover only from an exact linked source', () => {
    const hash = 'c'.repeat(64)
    render(
      <CaptureItemRow
        showVisualCover
        item={{
          id: 'capture:linked', root_path: '/Users/antman/inbox', relative_path: 'field-notes.pdf',
          filename: 'field-notes.pdf', extension: '.pdf', state: 'imported', sha256: hash,
          byte_size: 4_096, modified_ns: 1, reason: null,
          linked_source: {
            id: 'source:linked',
            visual: { source_id: 'source:linked', content_sha256: hash, asset_sha256: hash, alt_text: 'Imported field notes', width: 640, height: 360, mime_type: 'image/webp', asset_url: `/api/sources/source%3Alinked/visual?v=${hash}`, created_at: '2026-08-10T00:00:00Z', updated_at: '2026-08-10T00:01:00Z', origin: 'embedded', source_locator: { page: 1 } },
          },
        }}
      />,
    )

    expect(screen.getByRole('img', { name: /Imported field notes/ })).toBeVisible()
    expect(screen.queryByRole('button', { name: /visual/i })).not.toBeInTheDocument()
  })

  it('never infers a cover from an unlinked filename or path and keeps duplicate review routing', async () => {
    const route = vi.spyOn(captureApi, 'route').mockResolvedValue({
      state: 'ready', transcript: 'Local duplicate preview', notebook_suggestions: [], approval_required: true, reason: null,
    })
    render(
      <CaptureItemRow
        showVisualCover
        item={{
          id: 'capture:unlinked', root_path: '/Users/antman/inbox', relative_path: 'source-linked.mp3',
          filename: 'source-linked.mp3', extension: '.mp3', state: 'duplicate', sha256: 'd'.repeat(64),
          byte_size: 2_048, modified_ns: 2, reason: null, linked_source: null,
        }}
      />,
    )

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review route' }))
    await waitFor(() => expect(route).toHaveBeenCalledWith('/Users/antman/inbox/source-linked.mp3'))
    expect(await screen.findByText('Local duplicate preview')).toBeVisible()
    route.mockRestore()
  })

  it('keeps linked visuals hidden when the route-level gate is off', () => {
    render(
      <CaptureItemRow
        item={{
          id: 'capture:linked', root_path: '/Users/antman/inbox', relative_path: 'field-notes.pdf',
          filename: 'field-notes.pdf', extension: '.pdf', state: 'imported', sha256: 'e'.repeat(64),
          byte_size: 4_096, modified_ns: 1, reason: null,
          linked_source: { id: 'source:linked', visual: null },
        }}
      />,
    )
    expect(screen.queryByTestId('capture-linked-source-cover')).not.toBeInTheDocument()
  })

  it.each([
    ['both gates on', true, true, true],
    ['visual system off', false, true, false],
    ['source visuals off', true, false, false],
  ])('passes the exact Capture route visual gate when %s', (_label, visualSystem, sourceVisuals, visible) => {
    const hash = 'f'.repeat(64)
    mockVisualSystemEnabled.mockReturnValue(visualSystem)
    mockSourceVisualsEnabled.mockReturnValue(sourceVisuals)
    mockCaptureItems.current = [{
      id: 'capture:linked', root_path: '/Users/antman/inbox', relative_path: 'field-notes.pdf',
      filename: 'field-notes.pdf', extension: '.pdf', state: 'imported', sha256: hash,
      byte_size: 4_096, modified_ns: 1, reason: null,
      linked_source: {
        id: 'source:linked',
        visual: { source_id: 'source:linked', content_sha256: hash, asset_sha256: hash, alt_text: 'Imported field notes', width: 640, height: 360, mime_type: 'image/webp', asset_url: `/api/sources/source%3Alinked/visual?v=${hash}`, created_at: '2026-08-10T00:00:00Z', updated_at: '2026-08-10T00:01:00Z', origin: 'embedded', source_locator: { page: 1 } },
      },
    }]

    render(<CaptureInbox />)

    const cover = screen.queryByTestId('capture-linked-source-cover')
    if (visible) expect(cover).toBeInTheDocument()
    else expect(cover).not.toBeInTheDocument()
  })
})

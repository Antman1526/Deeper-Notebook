import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SourceCard } from './SourceCard'
import type { SourceListResponse } from '@/lib/types/api'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'

const mockUseSourceStatus = vi.hoisted(() => vi.fn())

vi.mock('@/lib/hooks/use-sources', () => ({
  useSourceStatus: mockUseSourceStatus,
}))

function source(overrides: Partial<SourceListResponse> = {}): SourceListResponse {
  return {
    id: 'source:1',
    title: 'Research source',
    asset: { url: 'https://example.com/research' },
    embedded: false,
    embedded_chunks: 0,
    insights_count: 0,
    created: '2026-06-23T00:00:00Z',
    updated: '2026-06-23T00:00:00Z',
    command_id: 'command:1',
    status: 'running',
    ...overrides,
  }
}

describe('SourceCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    usePodcastStudioStore.getState().dismiss()
    mockUseSourceStatus.mockReturnValue({
      data: {
        status: 'failed',
        message: 'Source processing failed',
        command_id: 'command:failed',
      },
      isLoading: false,
    })
  })

  it('retries a failed source without opening the source card', () => {
    const onRetry = vi.fn()
    const onClick = vi.fn()

    render(
      <SourceCard
        source={source({
          id: 'source:failed',
          title: 'Failed source',
          asset: { url: 'https://example.com/failed' },
          command_id: 'command:failed',
          status: 'failed',
        })}
        onRetry={onRetry}
        onClick={onClick}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'sources.retry' }))

    expect(onRetry).toHaveBeenCalledWith('source:failed')
    expect(onClick).not.toHaveBeenCalled()
  })

  it('shows a zero-percent progress bar for a newly running source', () => {
    mockUseSourceStatus.mockReturnValue({
      data: {
        status: 'running',
        message: 'Source processing in progress',
        command_id: 'command:running',
        processing_info: { progress: 0 },
      },
      isLoading: false,
    })

    render(<SourceCard source={source({ id: 'source:running' })} />)

    expect(screen.getByText('common.progress')).toBeInTheDocument()
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('uses source-list processing progress before status polling returns data', () => {
    mockUseSourceStatus.mockReturnValue({
      data: undefined,
      isLoading: false,
    })

    render(
      <SourceCard
        source={source({
          id: 'source:list-progress',
          status: 'running',
          processing_info: { progress: 25 },
        })}
      />
    )

    expect(screen.getByText('common.progress')).toBeInTheDocument()
    expect(screen.getByText('25%')).toBeInTheDocument()
  })

  it('derives source progress from processed and total item counts', () => {
    mockUseSourceStatus.mockReturnValue({
      data: {
        status: 'running',
        message: 'Source processing in progress',
        command_id: 'command:running',
        processing_info: { processed: 2, total: 4 },
      },
      isLoading: false,
    })

    render(<SourceCard source={source({ id: 'source:running' })} />)

    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('shows when an uploaded source original file is unavailable', () => {
    mockUseSourceStatus.mockReturnValue({
      data: undefined,
      isLoading: false,
    })

    render(
      <SourceCard
        source={source({
          id: 'source:missing-file',
          asset: { file_path: '/uploads/missing.pdf' },
          command_id: undefined,
          status: 'completed',
          embedded: true,
          file_available: false,
        })}
      />
    )

    expect(screen.getByText('sources.fileUnavailable')).toBeInTheDocument()
  })

  it('shows when a completed source has very little extracted text', () => {
    mockUseSourceStatus.mockReturnValue({
      data: undefined,
      isLoading: false,
    })

    render(
      <SourceCard
        source={source({
          id: 'source:thin-extract',
          asset: { file_path: '/uploads/scanned.pdf' },
          command_id: undefined,
          status: 'completed',
          embedded: false,
          extracted_char_count: 42,
          extraction_quality: 'low_text',
        })}
      />
    )

    expect(screen.getByText('sources.lowExtractedText')).toBeInTheDocument()
  })

  it('shows when a completed source has no extracted text', () => {
    mockUseSourceStatus.mockReturnValue({
      data: undefined,
      isLoading: false,
    })

    render(
      <SourceCard
        source={source({
          id: 'source:empty-extract',
          asset: { file_path: '/uploads/image-only.pdf' },
          command_id: undefined,
          status: 'completed',
          embedded: false,
          extracted_char_count: 0,
          extraction_quality: 'no_text',
        })}
      />
    )

    expect(screen.getByText('sources.noExtractedText')).toBeInTheDocument()
  })

  it('shows source labels, provenance, and shared notebook state', () => {
    mockUseSourceStatus.mockReturnValue({
      data: undefined,
      isLoading: false,
    })

    render(
      <SourceCard
        source={source({
          id: 'source:shared',
          command_id: undefined,
          status: 'completed',
          topics: ['training', 'policy'],
          provenance: { domain: 'academy.example.com' },
          notebook_count: 3,
          is_shared: true,
        })}
      />
    )

    expect(screen.getByText('Shared with 3')).toBeInTheDocument()
    expect(screen.getByText('academy.example.com')).toBeInTheDocument()
    expect(screen.getByText('training')).toBeInTheDocument()
    expect(screen.getByText('policy')).toBeInTheDocument()
  })

  it('opens an optional podcast review for a completed readable source', () => {
    mockUseSourceStatus.mockReturnValue({ data: undefined, isLoading: false })

    render(
      <SourceCard
        source={source({
          id: 'source:podcast-ready',
          command_id: undefined,
          status: 'completed',
          embedded: true,
        })}
      />
    )

    fireEvent.keyDown(screen.getByRole('button', { name: 'Source actions' }), {
      key: 'ArrowDown',
      code: 'ArrowDown',
    })
    fireEvent.click(screen.getByRole('menuitem', { name: 'Turn source into podcast' }))

    expect(usePodcastStudioStore.getState()).toMatchObject({
      isOpen: true,
      destination: 'quick',
      selections: [{ kind: 'app_source', sourceId: 'source:podcast-ready', inclusionMode: 'full' }],
    })
  })

  it('keeps the podcast action disabled when no readable content is available', () => {
    mockUseSourceStatus.mockReturnValue({ data: undefined, isLoading: false })

    render(
      <SourceCard
        source={source({
          id: 'source:podcast-empty',
          command_id: undefined,
          status: 'completed',
          extraction_quality: 'no_text',
        })}
      />
    )

    fireEvent.keyDown(screen.getByRole('button', { name: 'Source actions' }), {
      key: 'ArrowDown',
      code: 'ArrowDown',
    })

    expect(
      screen.getByRole('menuitem', { name: 'Turn source into podcast — No readable source content is available.' })
    ).toHaveAttribute('data-disabled')
    expect(usePodcastStudioStore.getState().isOpen).toBe(false)
  })

  it('does not retry a failed upload when the original file is unavailable', () => {
    mockUseSourceStatus.mockReturnValue({
      data: {
        status: 'failed',
        message: 'Source processing failed',
        command_id: 'command:failed',
      },
      isLoading: false,
    })
    const onRetry = vi.fn()

    render(
      <SourceCard
        source={source({
          id: 'source:missing-file',
          asset: { file_path: '/uploads/missing.pdf' },
          command_id: 'command:failed',
          status: 'failed',
          file_available: false,
        })}
        onRetry={onRetry}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'sources.retry' }))

    expect(screen.getByText('sources.fileUnavailable')).toBeInTheDocument()
    expect(onRetry).not.toHaveBeenCalled()
  })
})

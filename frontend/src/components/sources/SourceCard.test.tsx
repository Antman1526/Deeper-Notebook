import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SourceCard } from './SourceCard'
import type { SourceListResponse } from '@/lib/types/api'
import { usePodcastStudioStore } from '@/lib/stores/podcast-studio-store'

// v0.8.130 — resolve the real en-US strings (with {{name}} interpolation) so the
// counts, names and reasons below stay asserted after the strings moved to keys.
vi.mock('@/lib/hooks/use-translation', async () => {
  const { enUS } = await import('@/lib/locales/en-US')
  const resolve = (key: string, options?: Record<string, unknown>): string => {
    let node: unknown = enUS
    for (const part of key.split('.')) {
      if (typeof node !== 'object' || node === null || !(part in (node as Record<string, unknown>))) return key
      node = (node as Record<string, unknown>)[part]
    }
    if (typeof node !== 'string') return key
    return options
      ? node.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, name: string) => (name in options ? String(options[name]) : match))
      : node
  }
  return { useTranslation: () => ({ t: resolve, i18n: { language: 'en-US' }, language: 'en-US', setLanguage: async () => 'en-US' }) }
})

const mockUseSourceStatus = vi.hoisted(() => vi.fn())
const mockVisualSystemEnabled = vi.hoisted(() => vi.fn(() => false))
const mockSourceVisualsEnabled = vi.hoisted(() => vi.fn(() => false))

vi.mock('@/lib/hooks/use-sources', () => ({
  useSourceStatus: mockUseSourceStatus,
}))

vi.mock('@/lib/features', () => ({
  isVisualSystemV2Enabled: mockVisualSystemEnabled,
}))
vi.mock('@/lib/features-client', () => ({ useSourceVisualsEnabled: mockSourceVisualsEnabled }))

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
    mockVisualSystemEnabled.mockReturnValue(false)
    mockSourceVisualsEnabled.mockReturnValue(false)
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

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

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

    expect(screen.getByText('Progress')).toBeInTheDocument()
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

    expect(screen.getByText('Progress')).toBeInTheDocument()
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

    expect(screen.getByText('File unavailable')).toBeInTheDocument()
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

    expect(screen.getByText('Low extracted text')).toBeInTheDocument()
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

    expect(screen.getByText('No extracted text')).toBeInTheDocument()
  })

  // v0.8.130 — Phase 2d: a flat row (NotebookLM's source list), metadata as quiet text.
  it('renders a flat row whose metadata is text, not pills', () => {
    mockUseSourceStatus.mockReturnValue({ data: undefined, isLoading: false })

    const { container } = render(
      <SourceCard
        source={source({
          command_id: undefined,
          status: 'completed',
          insights_count: 2,
          topics: ['training', 'policy'],
          provenance: { domain: 'academy.example.com' },
          notebook_count: 3,
          is_shared: true,
        })}
      />
    )

    const row = container.querySelector('[data-dn-source-row]')
    expect(row).not.toBeNull()
    expect(row).not.toHaveAttribute('data-slot', 'card')
    expect(container.querySelector('[data-slot="badge"]')).toBeNull()
    expect(screen.getByRole('heading', { name: 'Research source' })).toHaveClass('truncate')
    expect(screen.getByText('training')).toBeInTheDocument()
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

  it('offers a separate review for stored source insights', () => {
    mockUseSourceStatus.mockReturnValue({ data: undefined, isLoading: false })

    render(
      <SourceCard
        source={source({
          id: 'source:podcast-insights',
          command_id: undefined,
          status: 'completed',
          insights_count: 2,
        })}
      />
    )

    fireEvent.keyDown(screen.getByRole('button', { name: 'Source actions' }), {
      key: 'ArrowDown',
      code: 'ArrowDown',
    })
    fireEvent.click(screen.getByRole('menuitem', { name: 'Turn source insights into podcast' }))

    expect(usePodcastStudioStore.getState().selections).toEqual([
      { kind: 'app_source', sourceId: 'source:podcast-insights', inclusionMode: 'insights' },
    ])
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

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(screen.getByText('File unavailable')).toBeInTheDocument()
    expect(onRetry).not.toHaveBeenCalled()
  })

  // v0.8.130 — Phase 2d: with neither an image nor a visual status, the fallback cover only
  // repeated the title above the row (and tripled its height).
  it('skips the cover when a source has no visual and no visual status', () => {
    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)
    mockUseSourceStatus.mockReturnValue({ data: undefined, isLoading: false })

    const { container } = render(
      <SourceCard source={source({ command_id: undefined, status: 'completed', visual: null, visual_status: null })} />
    )

    expect(container.querySelector('[data-dn-source-cover]')).toBeNull()
  })

  it('renders a compact source-derived cover only when both visual gates are enabled, without nested cover actions', () => {
    const hash = 'a'.repeat(64)
    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)
    mockUseSourceStatus.mockReturnValue({ data: undefined, isLoading: false })

    const { rerender } = render(
      <SourceCard source={source({
        id: 'source:visual', title: 'Visual source', command_id: undefined, status: 'completed',
        visual: {
          source_id: 'source:visual', content_sha256: hash, asset_sha256: hash,
          alt_text: 'Neutral source cover', width: 640, height: 360, mime_type: 'image/webp',
          asset_url: `/api/sources/source%3Avisual/visual?v=${hash}`,
          created_at: '2026-08-10T00:00:00Z', updated_at: '2026-08-10T00:00:00Z',
          origin: 'embedded', source_locator: { page: 1 },
        },
      } as never)} />,
    )

    expect(screen.getByRole('img', { name: 'Visual source — Embedded image: Neutral source cover' })).toBeVisible()
    expect(screen.queryByRole('button', { name: /Refresh visual|Remove visual|Open Visual source/ })).not.toBeInTheDocument()

    mockSourceVisualsEnabled.mockReturnValue(false)
    rerender(<SourceCard source={source({
      id: 'source:visual', title: 'Visual source', command_id: undefined, status: 'completed',
      visual: {
        source_id: 'source:visual', content_sha256: hash, asset_sha256: hash,
        alt_text: 'Neutral source cover', width: 640, height: 360, mime_type: 'image/webp',
        asset_url: `/api/sources/source%3Avisual/visual?v=${hash}`,
        created_at: '2026-08-10T00:00:00Z', updated_at: '2026-08-10T00:00:00Z',
        origin: 'embedded', source_locator: { page: 1 },
      },
    } as never)} />)
    expect(screen.queryByRole('img', { name: 'Visual source — Embedded image: Neutral source cover' })).not.toBeInTheDocument()
  })
})

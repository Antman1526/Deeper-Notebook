import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SourcesPage from './page'
import { sourcesApi } from '@/lib/api/sources'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'
import type { SourceListResponse } from '@/lib/types/api'

const { mockVisualSystemEnabled, mockSourceVisualsEnabled, mockRefreshVisual, mockRemoveVisual, mockRouterPush, mockConfirmDialog } = vi.hoisted(() => ({
  mockVisualSystemEnabled: vi.fn(() => false),
  mockSourceVisualsEnabled: vi.fn(() => false),
  mockRefreshVisual: vi.fn(),
  mockRemoveVisual: vi.fn(),
  mockRouterPush: vi.fn(),
  mockConfirmDialog: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockRouterPush }),
}))

vi.mock('@/components/layout/AppShell', () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('@/components/common/LoadingSpinner', () => ({
  LoadingSpinner: () => <div>Loading</div>,
}))

vi.mock('@/components/common/EmptyState', () => ({
  EmptyState: () => <div>Empty sources</div>,
}))

vi.mock('@/components/common/ConfirmDialog', () => ({
  ConfirmDialog: (props: unknown) => {
    mockConfirmDialog(props)
    return null
  },
}))

vi.mock('@/lib/api/sources', () => ({
  sourcesApi: {
    list: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: vi.fn(),
}))

vi.mock('@/lib/features', () => ({
  isVisualSystemV2Enabled: mockVisualSystemEnabled,
  isSourceVisualsEnabled: mockSourceVisualsEnabled,
}))

vi.mock('@/lib/hooks/use-source-visuals', () => ({
  useRefreshSourceVisual: () => ({ mutate: mockRefreshVisual }),
  useRemoveSourceVisual: () => ({ mutate: mockRemoveVisual }),
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    language: 'en-US',
    t: (key: string) => ({
      'sources.allSources': 'All sources',
      'sources.allSourcesDesc': 'Research sources ready to use.',
      'navigation.sources': 'Sources',
      'sources.addNew': 'Add source',
      'sources.delete': 'Delete source',
      'sources.deleteConfirmWithTitle': 'Delete {title}?',
      'common.type': 'Type',
      'common.title': 'Title',
      'common.created_label': 'Created',
      'sources.insights': 'Insights',
      'sources.embedded': 'Embedded',
      'common.actions': 'Actions',
      'sources.type.text': 'Text',
      'sources.yes': 'Yes',
      'sources.no': 'No',
    })[key] ?? key,
  }),
}))

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

describe('SourcesPage', () => {
  const openSourceDialog = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(sourcesApi.list).mockReset()
    mockVisualSystemEnabled.mockReturnValue(false)
    mockSourceVisualsEnabled.mockReturnValue(false)
    vi.mocked(useCreateDialogs).mockReturnValue({ openSourceDialog } as never)
    vi.mocked(sourcesApi.list).mockResolvedValue([
      {
        id: 'source:one',
        title: 'Field notes',
        source_type: 'text',
        created: '2026-08-10T00:00:00Z',
        updated: '2026-08-10T00:00:00Z',
        embedded: true,
        insights_count: 2,
      },
    ] as never)
  })

  it('keeps the sources table and add action inside the Collect folio frame', async () => {
    render(<SourcesPage />)

    expect(await screen.findByRole('main', { name: 'Sources' })).toBeInTheDocument()
    expect(screen.getByText('Collect')).toBeInTheDocument()
    expect(screen.getByText('Field notes')).toBeInTheDocument()
    expect(screen.getByRole('grid', { name: 'Sources' })).toHaveClass('min-w-[288px]')
    expect(screen.getByText('Field notes')).toHaveClass('block', 'min-w-0')
    fireEvent.click(screen.getByRole('button', { name: 'Add source' }))
    expect(openSourceDialog).toHaveBeenCalledWith(expect.objectContaining({
      onSourceCreated: expect.any(Function),
    }))
  })

  it('uses the adaptive gallery and one-shot visual actions only when both visual gates are on', async () => {
    const hash = 'a'.repeat(64)
    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)
    vi.mocked(sourcesApi.list).mockResolvedValueOnce([
      {
        id: 'source:one',
        title: 'Field notes',
        source_type: 'text',
        created: '2026-08-10T00:00:00Z',
        updated: '2026-08-10T00:00:00Z',
        embedded: true,
        insights_count: 2,
        visual: {
          source_id: 'source:one', content_sha256: hash, asset_sha256: hash,
          alt_text: 'Neutral source cover', width: 640, height: 360, mime_type: 'image/webp',
          asset_url: `/api/sources/source%3Aone/visual?v=${hash}`,
          created_at: '2026-08-10T00:00:00Z', updated_at: '2026-08-10T00:00:00Z',
          origin: 'embedded', source_locator: { page: 1 },
        },
      },
      {
        id: 'source:two',
        title: 'Appendix scan',
        source_type: 'text',
        created: '2026-08-10T00:00:00Z',
        updated: '2026-08-10T00:00:00Z',
        embedded: false,
        insights_count: 0,
        visual: null,
        visual_status: { state: 'unavailable' },
      },
    ] as never)

    render(<SourcesPage />)

    expect(await screen.findByLabelText('Source gallery')).toBeInTheDocument()
    expect(screen.getByTestId('source-gallery-card-source:one')).toHaveAttribute('data-featured', 'true')
    expect(screen.getByText('Embedded image')).toBeVisible()
    expect(screen.getByText('Visual cover unavailable')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh visual for Field notes' }))
    fireEvent.click(screen.getByRole('button', { name: 'Refresh visual for Field notes' }))
    expect(mockRefreshVisual).toHaveBeenCalledOnce()
    expect(mockRefreshVisual).toHaveBeenCalledWith('source:one', expect.objectContaining({ onSuccess: expect.any(Function) }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove visual for Appendix scan' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove visual for Appendix scan' }))
    expect(mockRemoveVisual).toHaveBeenCalledOnce()
    expect(mockRemoveVisual).toHaveBeenCalledWith('source:two', expect.objectContaining({ onSuccess: expect.any(Function) }))
  })

  it('keeps the existing source delete confirmation available for the selected gallery source', async () => {
    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)
    vi.mocked(sourcesApi.list).mockResolvedValueOnce([
      {
        id: 'source:one', title: 'Field notes', source_type: 'text', created: '2026-08-10T00:00:00Z', updated: '2026-08-10T00:00:00Z', embedded: true, insights_count: 0,
      },
      {
        id: 'source:two', title: 'Appendix scan', source_type: 'text', created: '2026-08-10T00:00:00Z', updated: '2026-08-10T00:00:00Z', embedded: false, insights_count: 0,
      },
    ] as never)

    render(<SourcesPage />)

    expect(await screen.findByLabelText('Source gallery')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Select Appendix scan' }))
    expect(screen.getByRole('button', { name: 'Created' })).toHaveClass('h-11', 'min-w-11')
    const deleteButton = screen.getByRole('button', { name: 'Delete source' })
    expect(deleteButton).toHaveClass('h-11', 'min-w-11')
    fireEvent.click(deleteButton)

    expect(mockConfirmDialog).toHaveBeenLastCalledWith(expect.objectContaining({
      open: true,
      title: 'Delete source',
      description: 'Delete Appendix scan?',
    }))
  })

  it('refetches the page-owned sources after successful visual mutations so covers update and pending clears', async () => {
    const firstUpdated = '2026-08-10T00:00:00Z'
    const refreshedUpdated = '2026-08-10T00:01:00Z'
    const removedUpdated = '2026-08-10T00:02:00Z'
    const firstStatusUpdated = '2026-08-10T00:00:01Z'
    const refreshedStatusUpdated = '2026-08-10T00:01:01Z'
    const removedStatusUpdated = '2026-08-10T00:02:01Z'
    const source = (overrides: Partial<SourceListResponse> = {}): SourceListResponse => ({
      id: 'source:one', title: 'Field notes', source_type: 'text', created: firstUpdated,
      updated: firstUpdated, asset: null, embedded: true, embedded_chunks: 0, insights_count: 0,
      visual_status: { state: 'processing', command_id: null, error_code: null, updated_at: firstStatusUpdated },
      ...overrides,
    })
    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)
    vi.mocked(sourcesApi.list)
      .mockResolvedValueOnce([source()])
      .mockResolvedValueOnce([source({ updated: refreshedUpdated, visual_status: { state: 'unavailable', command_id: null, error_code: null, updated_at: refreshedStatusUpdated } })])
      .mockResolvedValueOnce([source({ updated: removedUpdated, visual_status: { state: 'unavailable', command_id: null, error_code: null, updated_at: removedStatusUpdated }, visual: null })])
    let refreshSuccess: (() => void) | undefined
    let removeSuccess: (() => void) | undefined
    mockRefreshVisual.mockImplementation((_sourceId: string, options?: { onSuccess?: () => void }) => {
      refreshSuccess = options?.onSuccess
    })
    mockRemoveVisual.mockImplementation((_sourceId: string, options?: { onSuccess?: () => void }) => {
      removeSuccess = options?.onSuccess
    })

    render(<SourcesPage />)

    expect(await screen.findByText('Preparing visual cover')).toBeVisible()
    const refreshButton = screen.getByRole('button', { name: 'Refresh visual for Field notes' })
    fireEvent.click(refreshButton)
    expect(refreshButton).toBeDisabled()
    await act(async () => {
      refreshSuccess?.()
    })

    await waitFor(() => expect(sourcesApi.list).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('Visual cover unavailable')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Refresh visual for Field notes' })).not.toBeDisabled()

    const removeButton = screen.getByRole('button', { name: 'Remove visual for Field notes' })
    fireEvent.click(removeButton)
    expect(removeButton).toBeDisabled()
    await act(async () => {
      removeSuccess?.()
    })

    await waitFor(() => expect(sourcesApi.list).toHaveBeenCalledTimes(3))
    expect(screen.getByRole('button', { name: 'Remove visual for Field notes' })).not.toBeDisabled()
  })

  it('does not let gallery controls route through the page-global Enter handler', async () => {
    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)
    vi.mocked(sourcesApi.list).mockResolvedValueOnce([
      {
        id: 'source:one', title: 'Field notes', source_type: 'text', created: '2026-08-10T00:00:00Z', updated: '2026-08-10T00:00:00Z', embedded: true, insights_count: 0,
      },
    ] as never)

    render(<SourcesPage />)

    expect(await screen.findByLabelText('Source gallery')).toBeInTheDocument()
    fireEvent.keyDown(screen.getByRole('button', { name: 'Select Field notes' }), { key: 'Enter' })
    fireEvent.keyDown(screen.getByRole('button', { name: 'Open Field notes' }), { key: 'Enter' })
    fireEvent.keyDown(screen.getByRole('button', { name: 'Refresh visual for Field notes' }), { key: 'Enter' })
    fireEvent.keyDown(screen.getByRole('button', { name: 'Remove visual for Field notes' }), { key: 'Enter' })

    expect(mockRouterPush).not.toHaveBeenCalled()
  })

  it('keeps ArrowDown keyboard navigation scrolling the selected gallery card into view', async () => {
    const hash = 'a'.repeat(64)
    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)
    vi.mocked(sourcesApi.list).mockResolvedValueOnce([
      {
        id: 'source:one', title: 'Field notes', source_type: 'text', created: '2026-08-10T00:00:00Z', updated: '2026-08-10T00:00:00Z', embedded: true, insights_count: 0,
        visual: { source_id: 'source:one', content_sha256: hash, asset_sha256: hash, alt_text: 'Source one', width: 640, height: 360, mime_type: 'image/webp', asset_url: `/api/sources/source%3Aone/visual?v=${hash}`, created_at: '2026-08-10T00:00:00Z', updated_at: '2026-08-10T00:00:00Z', origin: 'embedded', source_locator: { page: 1 } },
      },
      {
        id: 'source:two', title: 'Appendix scan', source_type: 'text', created: '2026-08-10T00:00:00Z', updated: '2026-08-10T00:00:00Z', embedded: false, insights_count: 0,
      },
    ] as never)

    render(<SourcesPage />)

    const gallery = await screen.findByLabelText('Source gallery')
    const scrollSurface = gallery.closest('[data-dn-horizontal-scroll="sources-gallery"]') as HTMLDivElement
    const secondCard = screen.getByTestId('source-gallery-card-source:two')
    const scrollIntoView = vi.fn()
    Object.defineProperty(secondCard, 'scrollIntoView', { configurable: true, value: scrollIntoView })
    vi.spyOn(scrollSurface, 'getBoundingClientRect').mockReturnValue({ top: 0, bottom: 100 } as DOMRect)
    vi.spyOn(secondCard, 'getBoundingClientRect').mockReturnValue({ top: 150, bottom: 250 } as DOMRect)

    fireEvent.keyDown(window, { key: 'ArrowDown' })

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'end' }))
  })

  it.each([
    ['V2 off / source visuals on', false, true],
    ['V2 on / source visuals off', true, false],
  ])('keeps the exact table branch, keyboard, and source actions when %s', async (_label, visualSystemEnabled, sourceVisualsEnabled) => {
    mockVisualSystemEnabled.mockReturnValue(visualSystemEnabled)
    mockSourceVisualsEnabled.mockReturnValue(sourceVisualsEnabled)

    render(<SourcesPage />)

    expect(await screen.findByRole('grid', { name: 'Sources' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Source gallery')).not.toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(mockRouterPush).toHaveBeenCalledWith('/sources/source:one')
    fireEvent.click(screen.getByRole('button', { name: 'Delete source' }))
    expect(mockConfirmDialog).toHaveBeenLastCalledWith(expect.objectContaining({ open: true }))
    expect(mockRefreshVisual).not.toHaveBeenCalled()
    expect(mockRemoveVisual).not.toHaveBeenCalled()
  })
})

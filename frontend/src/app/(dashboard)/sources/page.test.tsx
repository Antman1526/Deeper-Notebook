import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    get: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: vi.fn(),
}))

vi.mock('@/lib/features', () => ({
  isVisualSystemV2Enabled: mockVisualSystemEnabled,
}))
vi.mock('@/lib/features-client', () => ({ useSourceVisualsEnabled: mockSourceVisualsEnabled }))

vi.mock('@/lib/hooks/use-source-visuals', () => ({
  useRefreshSourceVisual: () => ({ mutateAsync: mockRefreshVisual }),
  useRemoveSourceVisual: () => ({ mutateAsync: mockRemoveVisual }),
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

function closeOpenMenu() {
  const menu = screen.queryByRole('menu')
  if (menu) fireEvent.keyDown(menu, { key: 'Escape' })
}

describe('SourcesPage', () => {
  const openSourceDialog = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(sourcesApi.list).mockReset()
    vi.mocked(sourcesApi.get).mockReset()
    mockRefreshVisual.mockReset().mockResolvedValue(undefined)
    mockRemoveVisual.mockReset().mockResolvedValue(undefined)
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
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Field notes' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Refresh visual' }))
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Field notes' }))
    expect(screen.getByRole('menuitem', { name: 'Refresh visual' })).toHaveAttribute('aria-disabled', 'true')
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
    expect(mockRefreshVisual).toHaveBeenCalledOnce()
    expect(mockRefreshVisual).toHaveBeenCalledWith('source:one')
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Appendix scan' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove visual' }))
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Appendix scan' }))
    expect(screen.getByRole('menuitem', { name: 'Remove visual' })).toHaveAttribute('aria-disabled', 'true')
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
    expect(mockRemoveVisual).toHaveBeenCalledOnce()
    expect(mockRemoveVisual).toHaveBeenCalledWith('source:two')
  })

  it('opens confirmation for the menu source even when another gallery card is selected', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Field notes' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete source' }))

    expect(mockConfirmDialog).toHaveBeenLastCalledWith(expect.objectContaining({
      open: true,
      title: 'Delete source',
      description: 'Delete Field notes?',
    }))
  })

  it('refreshes the page-owned source after successful visual mutations so covers update and pending clears', async () => {
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
    vi.mocked(sourcesApi.list).mockResolvedValueOnce([source()])
    vi.mocked(sourcesApi.get)
      .mockResolvedValueOnce(source({ updated: refreshedUpdated, visual_status: { state: 'unavailable', command_id: null, error_code: null, updated_at: refreshedStatusUpdated } }) as never)
      .mockResolvedValueOnce(source({ updated: removedUpdated, visual_status: { state: 'unavailable', command_id: null, error_code: null, updated_at: removedStatusUpdated }, visual: null }) as never)
    render(<SourcesPage />)

    expect(await screen.findByText('Preparing visual cover')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Field notes' }))
    const refreshButton = screen.getByRole('menuitem', { name: 'Refresh visual' })
    fireEvent.click(refreshButton)

    await waitFor(() => expect(sourcesApi.get).toHaveBeenCalledWith('source:one'))
    expect(await screen.findByText('Visual cover unavailable')).toBeVisible()
    closeOpenMenu()
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Field notes' }))
    expect(screen.getByRole('menuitem', { name: 'Refresh visual' })).not.toHaveAttribute('aria-disabled', 'true')
    closeOpenMenu()

    fireEvent.click(screen.getByRole('button', { name: 'Actions for Field notes' }))
    const removeButton = screen.getByRole('menuitem', { name: 'Remove visual' })
    fireEvent.click(removeButton)

    await waitFor(() => expect(sourcesApi.get).toHaveBeenCalledTimes(2))
    closeOpenMenu()
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Field notes' }))
    expect(screen.getByRole('menuitem', { name: 'Remove visual' })).not.toHaveAttribute('aria-disabled', 'true')
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
    fireEvent.keyDown(screen.getByRole('button', { name: 'Actions for Field notes' }), { key: 'Enter' })
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })

    expect(mockRouterPush).not.toHaveBeenCalled()
  })

  it('preserves loaded gallery pages and selection while merging a later source mutation', async () => {
    const source = (index: number, overrides: Partial<SourceListResponse> = {}): SourceListResponse => ({
      id: `source:${index}`,
      title: `Source ${index}`,
      source_type: 'text',
      created: '2026-08-10T00:00:00Z',
      updated: '2026-08-10T00:00:00Z',
      asset: null,
      embedded: true,
      embedded_chunks: 0,
      insights_count: 0,
      ...overrides,
    })
    const firstPage = Array.from({ length: 30 }, (_, index) => source(index + 1))
    const secondPage = Array.from({ length: 30 }, (_, index) => source(index + 31))
    const continuationPage = [source(61)]
    const refreshedSource = source(45, {
      updated: '2026-08-10T01:00:00Z',
      visual: null,
      visual_status: {
        state: 'unavailable',
        command_id: null,
        error_code: null,
        updated_at: '2026-08-10T01:00:01Z',
      },
    })

    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)
    let scrollSurface: HTMLDivElement | null = null
    vi.mocked(sourcesApi.list).mockImplementation(async (params) => {
      switch (params?.offset ?? 0) {
        case 0:
          return firstPage
        case 30:
          if (scrollSurface) scrollSurface.scrollTop = 0
          return secondPage
        case 60:
          return continuationPage
        default:
          return []
      }
    })
    vi.mocked(sourcesApi.get).mockResolvedValue(refreshedSource as never)
    render(<SourcesPage />)

    const gallery = await screen.findByLabelText('Source gallery')
    scrollSurface = gallery.closest('[data-dn-horizontal-scroll="sources-gallery"]') as HTMLDivElement
    Object.defineProperties(scrollSurface, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 500 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    })
    scrollSurface.scrollTop = 600
    fireEvent.scroll(scrollSurface)
    await waitFor(() => {
      expect(screen.getByTestId('source-gallery-card-source:60')).toBeInTheDocument()
    })
    expect(sourcesApi.list).toHaveBeenNthCalledWith(2, expect.objectContaining({ offset: 30, limit: 30 }))

    fireEvent.click(screen.getByRole('button', { name: 'Select Source 45' }))
    expect(screen.getByRole('button', { name: 'Select Source 45' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Source 45' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Refresh visual' }))

    await waitFor(() => expect(sourcesApi.get).toHaveBeenCalledWith('source:45'))
    expect(sourcesApi.list).toHaveBeenCalledTimes(2)
    expect(screen.getByTestId('source-gallery-card-source:60')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Select Source 45' })).toHaveAttribute('aria-pressed', 'true')

    scrollSurface.scrollTop = 600
    fireEvent.scroll(scrollSurface)
    await waitFor(() => expect(sourcesApi.list).toHaveBeenCalledTimes(3))
    expect(sourcesApi.list).toHaveBeenNthCalledWith(3, expect.objectContaining({ offset: 60, limit: 30 }))
    expect(screen.getByTestId('source-gallery-card-source:61')).toBeInTheDocument()
  })

  it('preserves loaded gallery state when the authoritative mutation refresh fails', async () => {
    const source = (index: number): SourceListResponse => ({
      id: `source:${index}`,
      title: `Source ${index}`,
      source_type: 'text',
      created: '2026-08-10T00:00:00Z',
      updated: '2026-08-10T00:00:00Z',
      asset: null,
      embedded: true,
      embedded_chunks: 0,
      insights_count: 0,
    })
    const loadedSources = Array.from({ length: 31 }, (_, index) => source(index + 1))
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockVisualSystemEnabled.mockReturnValue(true)
    mockSourceVisualsEnabled.mockReturnValue(true)
    vi.mocked(sourcesApi.list).mockResolvedValueOnce(loadedSources as never)
    vi.mocked(sourcesApi.get).mockRejectedValue(new Error('source read unavailable'))
    try {
      render(<SourcesPage />)

      expect(await screen.findByTestId('source-gallery-card-source:31')).toBeInTheDocument()
      expect(screen.getAllByRole('listitem')).toHaveLength(31)
      fireEvent.click(screen.getByRole('button', { name: 'Select Source 31' }))
      fireEvent.click(screen.getByRole('button', { name: 'Actions for Source 31' }))
      fireEvent.click(screen.getByRole('menuitem', { name: 'Refresh visual' }))

      await waitFor(() => expect(sourcesApi.get).toHaveBeenCalledWith('source:31'))
      await waitFor(() => expect(consoleError).toHaveBeenCalledWith(
        'Failed to refresh source after visual mutation:',
        expect.any(Error),
      ))
      expect(sourcesApi.list).toHaveBeenCalledTimes(1)
      expect(screen.getAllByRole('listitem')).toHaveLength(31)
      expect(screen.getByTestId('source-gallery-card-source:30')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Select Source 31' })).toHaveAttribute('aria-pressed', 'true')
      await waitFor(() => expect(
        screen.getByRole('button', { name: 'Actions for Source 31' }),
      ).toBeInTheDocument())
    } finally {
      consoleError.mockRestore()
    }
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

    const grid = await screen.findByRole('grid', { name: 'Sources' })
    expect(screen.queryByLabelText('Source gallery')).not.toBeInTheDocument()
    await waitFor(() => expect(document.activeElement).toBe(grid))
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(mockRouterPush).toHaveBeenCalledWith('/sources/source:one')
    fireEvent.click(screen.getByRole('button', { name: 'Delete source' }))
    expect(mockConfirmDialog).toHaveBeenLastCalledWith(expect.objectContaining({ open: true }))
    expect(mockRefreshVisual).not.toHaveBeenCalled()
    expect(mockRemoveVisual).not.toHaveBeenCalled()
  })
})

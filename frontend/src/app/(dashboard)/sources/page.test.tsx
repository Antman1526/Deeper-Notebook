import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SourcesPage from './page'
import { sourcesApi } from '@/lib/api/sources'
import { useCreateDialogs } from '@/lib/hooks/use-create-dialogs'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
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
  ConfirmDialog: () => null,
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

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    language: 'en-US',
    t: (key: string) => ({
      'sources.allSources': 'All sources',
      'sources.allSourcesDesc': 'Research sources ready to use.',
      'navigation.sources': 'Sources',
      'sources.addNew': 'Add source',
      'sources.delete': 'Delete source',
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
})

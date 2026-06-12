// v0.7.119 — Refreshed to cover the expanded export dialog:
//   • the new format Select (now offers 6 values) renders + submits
//   • include_sources moved to the `notebooks.export.includeSources` key
//   • the compression Select only appears for zip / html_zip formats
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ExportNotebookDialog } from './ExportNotebookDialog'
import { useExportNotebook } from '@/lib/hooks/use-export'
import { useFsHome } from '@/lib/hooks/use-fs'

vi.mock('@/lib/hooks/use-export')
vi.mock('@/lib/hooks/use-fs', () => ({
  useFsHome: vi.fn(),
  useFsList: vi.fn(() => ({ data: null, isLoading: false, error: null })),
  useFsMkdir: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}))

function makeExportMock(overrides: Partial<ReturnType<typeof useExportNotebook>> = {}) {
  return {
    mutateAsync: vi.fn().mockResolvedValue({
      destination: '/Users/me/exports/x',
      format: 'folder',
      file_count: 3,
      total_bytes: 100,
      files: [],
      warnings: [],
    }),
    isPending: false,
    ...overrides,
  } as unknown as ReturnType<typeof useExportNotebook>
}

function makeHomeMock(overrides: Partial<ReturnType<typeof useFsHome>> = {}) {
  return {
    data: {
      home: '/Users/me',
      desktop: '/Users/me/Desktop',
      documents: '/Users/me/Documents',
      downloads: '/Users/me/Downloads',
      default_exports: '/Users/me/OpenNotebookPlus-Exports',
    },
    isLoading: false,
    error: null,
    ...overrides,
  } as unknown as ReturnType<typeof useFsHome>
}

describe('ExportNotebookDialog', () => {
  const baseProps = {
    open: true,
    onOpenChange: vi.fn(),
    notebookId: 'notebook:abc',
    notebookName: 'My Research Notes',
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useFsHome).mockReturnValue(makeHomeMock())
  })

  it('renders title and the combined-format Select trigger', () => {
    vi.mocked(useExportNotebook).mockReturnValue(makeExportMock())
    render(<ExportNotebookDialog {...baseProps} />)

    expect(screen.getByText('notebooks.exportNotebook')).toBeInTheDocument()
    // Trigger displays the default selected format label.
    expect(
      screen.getByLabelText('notebooks.exportFormatLabel'),
    ).toBeInTheDocument()
    expect(screen.getByText('notebooks.exportFormat.folder')).toBeInTheDocument()
  })

  it('seeds destination from default_exports + slugified notebook name', async () => {
    vi.mocked(useExportNotebook).mockReturnValue(makeExportMock())
    render(<ExportNotebookDialog {...baseProps} />)

    await waitFor(() => {
      const input = screen.getByLabelText('notebooks.exportDestination') as HTMLInputElement
      expect(input.value).toBe('/Users/me/OpenNotebookPlus-Exports/my-research-notes')
    })
  })

  it('submits with destination, format, include_sources, and overwrite', async () => {
    const exportMock = makeExportMock()
    vi.mocked(useExportNotebook).mockReturnValue(exportMock)
    render(<ExportNotebookDialog {...baseProps} />)

    await waitFor(() => {
      const input = screen.getByLabelText('notebooks.exportDestination') as HTMLInputElement
      expect(input.value).toContain('my-research-notes')
    })

    // v0.7.119 — include_sources moved to the new `notebooks.export.includeSources`
    // label. The folder format keeps the checkbox visible.
    fireEvent.click(screen.getByLabelText('notebooks.export.includeSources'))
    fireEvent.click(screen.getByLabelText('notebooks.exportOverwrite'))
    fireEvent.click(screen.getByText('notebooks.export.button'))

    await waitFor(() => {
      expect(exportMock.mutateAsync).toHaveBeenCalledWith({
        id: 'notebook:abc',
        data: expect.objectContaining({
          format: 'folder',
          include_sources: true,
          overwrite: true,
        }),
      })
    })
    // Folder format → no compression in the body.
    const mockFn = exportMock.mutateAsync as unknown as ReturnType<typeof vi.fn>
    const call = mockFn.mock.calls[0]?.[0] as
      | { data: Record<string, unknown> }
      | undefined
    expect(call?.data).not.toHaveProperty('compression')
  })

  it('hides the compression row for non-zip formats (combined_md default-render)', () => {
    vi.mocked(useExportNotebook).mockReturnValue(makeExportMock())
    render(<ExportNotebookDialog {...baseProps} />)

    // Default format is 'folder' — compression label must NOT be visible.
    expect(
      screen.queryByText('notebooks.export.compressionLabel'),
    ).not.toBeInTheDocument()
    // includeSources still renders for non-combined_html formats.
    expect(
      screen.getByLabelText('notebooks.export.includeSources'),
    ).toBeInTheDocument()
  })

  it('disables submit while the export is in flight', () => {
    vi.mocked(useExportNotebook).mockReturnValue(
      makeExportMock({ isPending: true } as Partial<ReturnType<typeof useExportNotebook>>),
    )
    render(<ExportNotebookDialog {...baseProps} />)

    const submitButton = screen.getByText('notebooks.exporting').closest('button')
    expect(submitButton).toBeDisabled()
  })

  it('closes the dialog after a successful export', async () => {
    const onOpenChange = vi.fn()
    vi.mocked(useExportNotebook).mockReturnValue(makeExportMock())
    render(<ExportNotebookDialog {...baseProps} onOpenChange={onOpenChange} />)

    await waitFor(() => {
      const input = screen.getByLabelText('notebooks.exportDestination') as HTMLInputElement
      expect(input.value).toContain('my-research-notes')
    })

    fireEvent.click(screen.getByText('notebooks.export.button'))

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false)
    })
  })
})

// v0.7.119 — Covers the preview → confirm → navigate flow and the
// yellow warnings banner from /notebooks/import/preview.
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

import { ImportNotebookDialog } from './ImportNotebookDialog'

vi.mock('@/lib/hooks/use-fs', () => ({
  useFsHome: vi.fn(() => ({
    data: {
      home: '/Users/me',
      desktop: '/Users/me/Desktop',
      documents: '/Users/me/Documents',
      downloads: '/Users/me/Downloads',
      default_exports: '/Users/me/OpenNotebookPlus-Exports',
    },
  })),
  useFsList: vi.fn(() => ({ data: null, isLoading: false, error: null })),
  useFsMkdir: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}))

const previewMutateAsync = vi.fn()
const importMutateAsync = vi.fn()

vi.mock('@/lib/hooks/use-notebooks', () => ({
  useImportPreview: () => ({
    mutateAsync: previewMutateAsync,
    isPending: false,
    reset: vi.fn(),
  }),
  useImportNotebook: () => ({
    mutateAsync: importMutateAsync,
    isPending: false,
    reset: vi.fn(),
  }),
  useNotebooks: () => ({
    data: [
      { id: 'notebook:existing', name: 'Existing notebook' },
    ],
  }),
}))

const pushMock = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/notebooks',
}))

describe('ImportNotebookDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    pushMock.mockClear()
    previewMutateAsync.mockReset()
    importMutateAsync.mockReset()
  })

  it('runs preview, surfaces warnings, then confirms and navigates', async () => {
    previewMutateAsync.mockResolvedValueOnce({
      source_path: '/tmp/bundle',
      detected_kind: 'folder',
      notebook_name_hint: 'Research Bundle',
      description_hint: 'Imported set',
      notes: [
        { relative_path: '00-overview.md', title: 'Overview', bytes: 42, is_overview: true },
        { relative_path: 'note1.md', title: 'Note 1', bytes: 120, is_overview: false },
      ],
      sources: [
        { relative_path: 'sources/src.md', title: 'Source 1', bytes: 88, is_overview: false },
      ],
      has_manifest: true,
      total_bytes: 250,
      warnings: ['manifest.json present but invalid: foo'],
    })
    importMutateAsync.mockResolvedValueOnce({
      notebook_id: 'notebook:fresh',
      notebook_name: 'Research Bundle',
      mode: 'new',
      note_ids: ['note:1', 'note:2'],
      source_ids: ['source:1'],
      file_count: 3,
      items: [],
      warnings: [],
    })

    const onOpenChange = vi.fn()
    render(
      <ImportNotebookDialog open onOpenChange={onOpenChange} />,
    )

    // Type a source path and trigger Preview.
    const pathInput = screen.getByLabelText('notebooks.import.sourcePathLabel')
    fireEvent.change(pathInput, { target: { value: '/tmp/bundle' } })

    fireEvent.click(screen.getByText('notebooks.import.preview'))

    await waitFor(() => {
      expect(previewMutateAsync).toHaveBeenCalledWith({ source_path: '/tmp/bundle' })
    })

    // Detected kind badge + warning surface in the dialog.
    await screen.findByTestId('import-detected-kind')
    expect(screen.getByTestId('import-detected-kind')).toHaveTextContent('folder')
    expect(
      screen.getByText('manifest.json present but invalid: foo'),
    ).toBeInTheDocument()

    // Name prefilled from hint.
    const nameInput = screen.getByLabelText(
      'notebooks.import.newNameLabel',
    ) as HTMLInputElement
    expect(nameInput.value).toBe('Research Bundle')

    // Confirm import → mutates with the expected body.
    fireEvent.click(screen.getByText('notebooks.import.confirm'))

    await waitFor(() => {
      expect(importMutateAsync).toHaveBeenCalledWith({
        source_path: '/tmp/bundle',
        mode: 'new',
        target_notebook_id: null,
        new_name: 'Research Bundle',
        import_sources: true,
      })
    })

    // On success: dialog closes + router redirects to the new notebook.
    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false)
      expect(pushMock).toHaveBeenCalledWith('/notebooks/notebook:fresh')
    })
  })

  it('disables Confirm until preview succeeds', () => {
    render(<ImportNotebookDialog open onOpenChange={vi.fn()} />)

    const confirmBtn = screen.getByText('notebooks.import.confirm').closest('button')
    expect(confirmBtn).toBeDisabled()
  })
})

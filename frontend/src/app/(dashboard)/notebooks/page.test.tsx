import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import NotebooksPage from './page'

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/lib/hooks/use-notebooks', () => ({ useNotebooks: () => ({ data: [], isLoading: false, refetch: vi.fn() }) }))
vi.mock('@/lib/hooks/use-sample-notebook', () => ({ useCreateSampleNotebook: () => ({ create: vi.fn(), pending: false }) }))
vi.mock('@/components/notebooks/CreateNotebookDialog', () => ({
  CreateNotebookDialog: ({ onOpenChange }: { onOpenChange: (open: boolean) => void }) => (
    <button type="button" data-testid="close-create-dialog" onClick={() => onOpenChange(false)}>
      Close create dialog
    </button>
  ),
}))
vi.mock('./components/ImportNotebookDialog', () => ({ ImportNotebookDialog: () => null }))
vi.mock('./components/NotebookList', () => ({ NotebookList: ({ title }: { title: string }) => <section>{title}</section> }))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'notebooks.title': 'Notebooks',
      'notebooks.activeNotebooks': 'Active notebooks',
      'notebooks.import.button': 'Import',
      'notebooks.newNotebook': 'New Notebook',
      'common.accessibility.searchNotebooks': 'Search notebooks',
    })[key] ?? key,
  }),
}))

describe('NotebooksPage', () => {
  it('keeps the notebook search, import, and creation controls in an Organize folio', () => {
    render(<NotebooksPage />)

    expect(screen.getByRole('main', { name: 'Notebooks' })).toBeInTheDocument()
    expect(screen.getByText('Organize')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Search notebooks' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New Notebook' })).toBeInTheDocument()
  })

  it('returns focus to the notebook trigger when the dialog closes', async () => {
    render(<NotebooksPage />)

    const trigger = screen.getByRole('button', { name: 'New Notebook' })
    trigger.focus()
    fireEvent.click(screen.getByTestId('close-create-dialog'))

    await waitFor(() => expect(trigger).toHaveFocus())
  })
})

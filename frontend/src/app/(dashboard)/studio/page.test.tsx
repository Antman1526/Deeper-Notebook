import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  generate: vi.fn(),
  coursePack: vi.fn(),
  push: vi.fn(),
}))

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: state.push }) }))
vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return { ...actual, useQuery: () => ({ data: [] }) }
})
vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/lib/hooks/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('@/lib/hooks/use-translation', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('@/lib/hooks/use-studio', () => ({
  useStudioGenerate: () => ({ mutateAsync: state.generate, isPending: false, isError: false, error: null }),
  useStudioCoursePack: () => ({ mutateAsync: state.coursePack, isPending: false, isError: false, error: null }),
}))

import StudioPage from './page'

describe('Evidence Studio folio integration', () => {
  beforeEach(() => {
    state.generate.mockReset()
    state.coursePack.mockReset()
    state.push.mockReset()
    state.generate.mockResolvedValue({ warnings: [], notebook_id: 'notebook:generated', job_id: 'job:generated' })
  })

  it('keeps source, brief, and explicit generation controls in the folio without requesting on mount', () => {
    render(<StudioPage />)

    expect(screen.getByRole('main', { name: 'Evidence Studio folio' })).toBeInTheDocument()
    expect(screen.getByLabelText('Source desk')).toHaveTextContent('studio.step1Title')
    expect(screen.getByLabelText('Editorial brief')).toHaveTextContent('studio.step2Title')
    expect(screen.getByRole('button', { name: 'studio.generateNotebook' })).toBeDisabled()
    expect(state.generate).not.toHaveBeenCalled()
    expect(state.coursePack).not.toHaveBeenCalled()
  })

  it('keeps generation explicit after a source is supplied', async () => {
    render(<StudioPage />)
    fireEvent.change(screen.getByLabelText('studio.linksLabel'), {
      target: { value: 'https://example.com/research' },
    })

    const generate = screen.getByRole('button', { name: 'studio.generateNotebook' })
    expect(generate).toBeEnabled()
    fireEvent.click(generate)

    await waitFor(() => expect(state.generate).toHaveBeenCalledWith(expect.objectContaining({
      links: ['https://example.com/research'], mode: 'notebook',
    })))
    expect(state.push).toHaveBeenCalledWith('/notebooks/notebook%3Agenerated')
  })

  it('sizes the mode picker from its own available width instead of the viewport', () => {
    render(<StudioPage />)

    const notebookMode = screen.getByRole('button', {
      name: /studio\.notebookModeTitle studio\.notebookModeDescription/,
    })
    expect(notebookMode.parentElement).toHaveStyle({
      gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 12rem), 1fr))',
    })
  })
})

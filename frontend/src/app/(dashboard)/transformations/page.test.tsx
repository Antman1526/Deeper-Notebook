import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import TransformationsPage from './page'

vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/lib/hooks/use-transformations', () => ({ useTransformations: () => ({ data: [], isLoading: false, refetch: vi.fn() }) }))
vi.mock('./components/DefaultPromptEditor', () => ({ DefaultPromptEditor: () => <div>Prompt editor</div> }))
vi.mock('./components/TransformationsList', () => ({ TransformationsList: () => <div>Transformation list</div> }))
vi.mock('./components/TransformationPlayground', () => ({ TransformationPlayground: () => <div>Playground</div> }))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string) => ({
    'transformations.desc': 'Reusable research transformations.',
    'transformations.workspace': 'Workspace',
    'transformations.title': 'Transformations',
  })[key] ?? key }),
}))

describe('TransformationsPage', () => {
  it('keeps the prompt editor and transformation list inside a Create folio', () => {
    render(<TransformationsPage />)
    expect(screen.getByRole('main', { name: 'Transformations' })).toBeInTheDocument()
    expect(screen.getByText('Create')).toBeInTheDocument()
    expect(screen.getByText('Prompt editor')).toBeInTheDocument()
    expect(screen.getByText('Transformation list')).toBeInTheDocument()
  })
})

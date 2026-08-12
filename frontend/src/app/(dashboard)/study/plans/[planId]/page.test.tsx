import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import StudyPlanPage from './page'

vi.mock('next/navigation', () => ({
  useParams: () => ({ planId: 'study_plan:one' }),
  useSearchParams: () => new URLSearchParams('tab=overview'),
}))
vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/study/StudyPlanWorkspace', () => ({
  StudyPlanWorkspace: ({ planId }: { planId: string }) => <div data-testid="workspace">{planId}</div>,
}))

describe('StudyPlanPage', () => {
  it('provides one named main landmark and a bounded plan workspace in either shell mode', () => {
    render(<StudyPlanPage />)

    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getByRole('main', { name: 'Study' })).toBeInTheDocument()
    expect(screen.getByTestId('workspace')).toHaveTextContent('study_plan:one')
  })
})

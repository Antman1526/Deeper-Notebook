import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import StudyPlanPage from './page'

const featureFlags = vi.hoisted(() => ({
  isStudyWorkbenchEnabled: vi.fn(() => true),
}))

vi.mock('@/lib/features', () => featureFlags)

vi.mock('next/navigation', () => ({
  useParams: () => ({ planId: 'study_plan:one' }),
  useSearchParams: () => new URLSearchParams('tab=overview'),
}))
vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/study/StudyPlanWorkspace', () => ({
  StudyPlanWorkspace: ({ planId }: { planId: string }) => <div data-testid="workspace">{planId}</div>,
}))

describe('StudyPlanPage', () => {
  beforeEach(() => {
    featureFlags.isStudyWorkbenchEnabled.mockReturnValue(true)
  })

  it('provides one named main landmark and a bounded plan workspace in either shell mode', () => {
    render(<StudyPlanPage />)

    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getByRole('main', { name: 'Study' })).toBeInTheDocument()
    expect(screen.getByTestId('workspace')).toHaveTextContent('study_plan:one')
  })

  it('does not mount the dynamic workbench route when the Study flag is off', () => {
    featureFlags.isStudyWorkbenchEnabled.mockReturnValue(false)

    render(<StudyPlanPage />)

    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getByRole('heading', { level: 1 })).toBeVisible()
    expect(screen.queryByTestId('workspace')).toBeNull()
  })
})

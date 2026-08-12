import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import StudyPage from './page'

vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/study/StudyDashboard', () => ({ StudyDashboard: () => <div>Study dashboard</div> }))
vi.mock('@/components/study/StudySession', () => ({ StudySession: () => <div>Study session</div> }))
vi.mock('@/lib/hooks/use-study', () => ({ useDueStudyCards: () => ({ data: [], isError: false, isLoading: false }) }))

describe('StudyPage', () => {
  it('keeps the existing local study dashboard and session inside a Discover folio', () => {
    render(<StudyPage />)

    expect(screen.getByRole('main', { name: 'Study' })).toBeInTheDocument()
    expect(screen.getByText('Discover')).toBeInTheDocument()
    expect(screen.getByText('Study dashboard')).toBeInTheDocument()
    expect(screen.getByText('Study session')).toBeInTheDocument()
  })

  it('keeps the current Study review surface when the workbench flag is off', () => {
    process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = '0'

    render(<StudyPage />)

    expect(screen.getByText('Study dashboard')).toBeInTheDocument()
    expect(screen.getByText('Study session')).toBeInTheDocument()
  })
})

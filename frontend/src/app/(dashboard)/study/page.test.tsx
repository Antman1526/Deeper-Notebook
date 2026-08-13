import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import StudyPage from './page'

const studyHook = vi.hoisted(() => ({
  useDueStudyCards: vi.fn(() => ({ data: [], isError: false, isLoading: false })),
}))

vi.mock('@/components/layout/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/study/StudyDashboard', () => ({ StudyDashboard: () => <div>Study dashboard</div> }))
vi.mock('@/components/study/StudySession', () => ({ StudySession: () => <div>Study session</div> }))
vi.mock('@/components/study/StudyWorkbench', () => ({ StudyWorkbench: () => <div>Study workbench</div> }))
vi.mock('@/lib/hooks/use-study', () => studyHook)

describe('StudyPage', () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH
    studyHook.useDueStudyCards.mockClear()
  })

  it('keeps the existing local study dashboard and session inside a Discover folio', () => {
    process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = '0'

    render(<StudyPage />)

    expect(screen.getByRole('main', { name: 'Study' })).toBeInTheDocument()
    expect(screen.getByText('Discover')).toBeInTheDocument()
    expect(screen.getByText('Study dashboard')).toBeInTheDocument()
    expect(screen.getByText('Study session')).toBeInTheDocument()
  })

  it('enables the Study Workbench by default while keeping due-card loading bounded', () => {
    delete process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH

    render(<StudyPage />)

    expect(screen.getByText('Study workbench')).toBeInTheDocument()
    expect(studyHook.useDueStudyCards).toHaveBeenCalledWith(true)
  })

  it('keeps the current Study review surface when the workbench flag is off', () => {
    process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = '0'

    render(<StudyPage />)

    expect(screen.getByText('Study dashboard')).toBeInTheDocument()
    expect(screen.getByText('Study session')).toBeInTheDocument()
    expect(studyHook.useDueStudyCards).toHaveBeenCalledWith(false)
  })

  it('enables due-card loading when the Study workbench flag is on', () => {
    process.env.NEXT_PUBLIC_DN_STUDY_WORKBENCH = '1'

    render(<StudyPage />)

    expect(studyHook.useDueStudyCards).toHaveBeenCalledWith(true)
  })
})

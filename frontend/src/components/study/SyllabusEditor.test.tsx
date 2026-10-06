import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  StudyPlan,
  StudySourceReadiness,
  StudySyllabus,
} from '@/lib/types/study-plans'
import { SyllabusEditor } from './SyllabusEditor'

const saveSyllabus = vi.fn()
const approveSyllabus = vi.fn()
const refresh = vi.fn()

// Interpolated values are part of what these tests assert (version numbers,
// unit titles, counts), so this mock renders `key(value1,value2)` rather than
// the bare key used by the global setup mock.
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => (
      options ? `${key}(${Object.values(options).join(',')})` : key
    ),
  }),
}))

vi.mock('@/lib/hooks/use-study-plans', () => ({
  useSaveStudySyllabus: () => ({ mutateAsync: saveSyllabus, isPending: false }),
  useApproveStudySyllabus: () => ({ mutateAsync: approveSyllabus, isPending: false }),
}))

const PLAN: StudyPlan = {
  plan_id: 'study_plan:one',
  goal: 'Understand mechanics',
  starting_level: 'beginner',
  target_date: null,
  preferences: null,
  source_links: [{ source_id: 'source:one' }, { source_id: 'source:two' }],
  approved_syllabus_version: null,
  state: 'editing',
  version: 4,
  created_at: '2026-08-12T12:00:00Z',
  updated_at: '2026-08-12T12:00:00Z',
}

const SYLLABUS: StudySyllabus = {
  plan_id: PLAN.plan_id,
  version: 2,
  source_manifest_sha256: 'a'.repeat(64),
  approved_at: null,
  units: [
    {
      unit_id: 'foundations',
      title: 'Foundations',
      objectives: ['Explain the core terms'],
      prerequisite_unit_ids: [],
      estimated_minutes: 30,
      source_ids: ['source:one', 'source:two'],
      activities: [],
    },
    {
      unit_id: 'practice',
      title: 'Practice',
      objectives: ['Apply the core terms'],
      prerequisite_unit_ids: ['foundations'],
      estimated_minutes: 30,
      source_ids: ['source:one'],
      activities: [],
    },
  ],
}

const READY: StudySourceReadiness = {
  ready: true,
  items: [
    {
      source_id: 'source:one',
      title: 'Lecture notes',
      kind: 'upload',
      ready: true,
      command_id: null,
      fingerprint_status: 'available',
      reason: 'ready',
    },
    {
      source_id: 'source:two',
      title: 'Textbook',
      kind: 'text',
      ready: true,
      command_id: null,
      fingerprint_status: 'available',
      reason: 'ready',
    },
  ],
}

describe('SyllabusEditor', () => {
  beforeEach(() => {
    saveSyllabus.mockReset()
    approveSyllabus.mockReset()
    refresh.mockReset()
    saveSyllabus.mockResolvedValue(SYLLABUS)
    approveSyllabus.mockResolvedValue({ ...PLAN, state: 'approved', approved_syllabus_version: 2 })
  })

  it('shows source coverage and gaps and approves only the displayed version after confirmation', async () => {
    render(<SyllabusEditor plan={PLAN} syllabus={SYLLABUS} readiness={READY} onRefresh={refresh} />)

    expect(screen.getByText('study.syllabusEditor.coverageCount(2,2)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'study.syllabusEditor.approveVersion(2)' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'study.syllabusEditor.approveVersion(2)' }))
    expect(screen.getByText('study.syllabusEditor.approveDialogTitle(2)')).toBeInTheDocument()
    expect(screen.getByText('study.syllabusEditor.approveDialogDescription(2,2,2)')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'study.syllabusEditor.confirmApproval' }))

    await waitFor(() => expect(approveSyllabus).toHaveBeenCalledWith({
      planId: PLAN.plan_id,
      input: { syllabus_version: 2, expected_revision: PLAN.version },
    }))
  })

  it('blocks approval while any linked source is processing or fingerprint-drifted', () => {
    const blocked: StudySourceReadiness = {
      ...READY,
      ready: false,
      items: [
        READY.items[0],
        { ...READY.items[1], ready: false, fingerprint_status: 'unknown', reason: 'processing' },
      ],
    }
    render(<SyllabusEditor plan={PLAN} syllabus={SYLLABUS} readiness={blocked} onRefresh={refresh} />)

    expect(screen.getByText('study.syllabusEditor.block.sourceNotReady')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'study.syllabusEditor.approveVersion(2)' })).toBeDisabled()
  })

  it('reorders units with keyboard-accessible buttons and saves an immutable next version', async () => {
    render(<SyllabusEditor plan={PLAN} syllabus={SYLLABUS} readiness={READY} onRefresh={refresh} />)

    fireEvent.click(screen.getByRole('button', { name: 'study.syllabusEditor.moveUpAria(Practice)' }))

    await waitFor(() => expect(saveSyllabus).toHaveBeenCalledWith({
      planId: PLAN.plan_id,
      input: expect.objectContaining({
        expected_revision: PLAN.version,
        version: 3,
        source_manifest_sha256: SYLLABUS.source_manifest_sha256,
        units: [SYLLABUS.units[1], SYLLABUS.units[0]],
      }),
    }))
    expect(screen.getByText('study.syllabusEditor.versionImmutable(3)')).toBeInTheDocument()
  })

  it('binds approval to the newly saved immutable version and monotonic revision', async () => {
    render(<SyllabusEditor plan={PLAN} syllabus={SYLLABUS} readiness={READY} onRefresh={refresh} />)

    fireEvent.click(screen.getByRole('button', { name: 'study.syllabusEditor.moveUpAria(Practice)' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'study.syllabusEditor.approveVersion(3)' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'study.syllabusEditor.approveVersion(3)' }))
    fireEvent.click(screen.getByRole('button', { name: 'study.syllabusEditor.confirmApproval' }))

    await waitFor(() => expect(approveSyllabus).toHaveBeenCalledWith({
      planId: PLAN.plan_id,
      input: { syllabus_version: 3, expected_revision: PLAN.version + 1 },
    }))
  })

  it('offers refresh recovery after a stale revision conflict', async () => {
    approveSyllabus.mockRejectedValueOnce({ response: { status: 409 } })
    render(<SyllabusEditor plan={PLAN} syllabus={SYLLABUS} readiness={READY} onRefresh={refresh} />)

    fireEvent.click(screen.getByRole('button', { name: 'study.syllabusEditor.approveVersion(2)' }))
    fireEvent.click(screen.getByRole('button', { name: 'study.syllabusEditor.confirmApproval' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('study.syllabusEditor.errors.changedElsewhere')
      expect(screen.getByRole('button', { name: 'study.syllabusEditor.refreshSyllabus' })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: 'study.syllabusEditor.refreshSyllabus' }))
    expect(refresh).toHaveBeenCalledOnce()
  })
})

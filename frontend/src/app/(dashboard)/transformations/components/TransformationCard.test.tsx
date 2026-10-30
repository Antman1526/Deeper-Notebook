import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Transformation } from '@/lib/types/transformations'

import { TransformationCard } from './TransformationCard'

// T0-7 — the delete confirmation for a transformation was titled with the
// source-specific key ("Delete Source"). It must use the generic delete title.

let confirmProps: { title?: string; description?: string } = {}

vi.mock('@/components/common/ConfirmDialog', () => ({
  ConfirmDialog: (props: { title: string; description: string }) => {
    confirmProps = props
    return null
  },
}))
vi.mock('@/lib/hooks/use-transformations', () => ({
  useDeleteTransformation: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const transformation: Transformation = {
  id: 'transformation:one',
  name: 'summarize',
  title: 'Summarize',
  description: 'Condense a source.',
  prompt: 'Summarize the text.',
  apply_default: false,
  created: '2026-01-01T00:00:00Z',
  updated: '2026-01-01T00:00:00Z',
}

describe('TransformationCard delete confirmation', () => {
  it('is not titled with the source-specific "Delete Source" key', () => {
    render(<TransformationCard transformation={transformation} />)

    expect(confirmProps.title).not.toBe('sources.delete')
    expect(confirmProps.title).toBe('common.delete')
    expect(confirmProps.description).toBe('transformations.deleteConfirm')
  })
})

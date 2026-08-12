import React, { useEffect } from 'react'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const testState = vi.hoisted(() => ({ sourceType: 'text' as 'text' | 'link' }))
const mutateAsync = vi.fn()

vi.mock('@/lib/hooks/use-sources', () => ({
  useCreateSource: () => ({ mutateAsync, isPending: false }),
}))
vi.mock('@/lib/hooks/use-notebooks', () => ({ useNotebooks: () => ({ data: [], isLoading: false }) }))
vi.mock('@/lib/hooks/use-transformations', () => ({ useTransformations: () => ({ data: [], isLoading: false }) }))
vi.mock('@/lib/hooks/use-settings', () => ({ useSettings: () => ({ data: undefined }) }))
vi.mock('@/lib/hooks/use-translation', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
vi.mock('@/lib/config', () => ({ getConfig: vi.fn().mockResolvedValue({}) }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h1>{children}</h1>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}))
vi.mock('@/components/ui/wizard-container', () => ({
  WizardContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('./steps/SourceTypeStep', () => ({
  SourceTypeStep: ({ setValue }: { setValue: (name: string, value: unknown) => void }) => {
    useEffect(() => {
      setValue('type', testState.sourceType)
      if (testState.sourceType === 'link') {
        setValue('url', 'https://one.test\nhttps://two.test')
      } else {
        setValue('title', 'Study note')
        setValue('content', 'A bounded source body for the test.')
      }
    }, [setValue])
    return <div data-testid="source-type-step" />
  },
  filesFromInput: () => [],
  getOversizedFiles: () => [],
  parseAndValidateUrls: () => ({ valid: ['https://one.test', 'https://two.test'], invalid: [] }),
}))
vi.mock('./steps/NotebooksStep', () => ({ NotebooksStep: () => null }))
vi.mock('./steps/ProcessingStep', () => ({ ProcessingStep: () => null }))

import { AddSourceDialog } from './AddSourceDialog'

describe('AddSourceDialog source-created callback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    testState.sourceType = 'text'
    mutateAsync.mockResolvedValue({ id: 'source:created' })
  })

  it('calls the legacy callback once and reports one bounded ID batch for a single source', async () => {
    const onSourceCreated = vi.fn()
    const onSourcesCreated = vi.fn()
    render(
      <AddSourceDialog
        open
        onOpenChange={vi.fn()}
        onSourceCreated={onSourceCreated}
        onSourcesCreated={onSourcesCreated}
      />,
    )

    await waitFor(() => expect(screen.getByRole('button', { name: 'common.done' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'common.done' }))

    await waitFor(() => {
      expect(onSourceCreated).toHaveBeenCalledOnce()
      expect(onSourceCreated).toHaveBeenCalledWith()
      expect(onSourcesCreated).toHaveBeenCalledOnce()
      expect(onSourcesCreated).toHaveBeenCalledWith(['source:created'])
    })
  })

  it('calls each callback once for a batch and reports all bounded IDs together', async () => {
    testState.sourceType = 'link'
    mutateAsync
      .mockResolvedValueOnce({ id: 'source:first' })
      .mockResolvedValueOnce({ id: 'source:second' })
    const onSourceCreated = vi.fn()
    const onSourcesCreated = vi.fn()
    render(
      <AddSourceDialog
        open
        onOpenChange={vi.fn()}
        onSourceCreated={onSourceCreated}
        onSourcesCreated={onSourcesCreated}
      />,
    )

    await waitFor(() => expect(screen.getByRole('button', { name: 'common.done' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'common.done' }))

    await waitFor(() => {
      expect(onSourceCreated).toHaveBeenCalledOnce()
      expect(onSourceCreated).toHaveBeenCalledWith()
      expect(onSourcesCreated).toHaveBeenCalledOnce()
      expect(onSourcesCreated).toHaveBeenCalledWith(['source:first', 'source:second'])
    })
  })
})

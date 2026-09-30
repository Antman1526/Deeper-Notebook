import React from 'react'

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

// T0-11 — one translation key ("Content will be processed and analyzed by AI.")
// was reused for the dialog subtitle, two wizard step descriptions, the Sources
// section, the active tab and both processing sections, so the same sentence
// showed up four times on the first step. It appears once, in the header.

vi.mock('@/lib/hooks/use-sources', () => ({
  useCreateSource: () => ({ mutateAsync: vi.fn(), isPending: false }),
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

import { useForm } from 'react-hook-form'

import { WizardContainer } from '@/components/ui/wizard-container'

import { AddSourceDialog } from './AddSourceDialog'
import { ProcessingStep } from './steps/ProcessingStep'

const SENTENCE_KEY = 'sources.processDescription'

describe('AddSourceDialog copy', () => {
  it('states the processing sentence once on the first step, not in every section', () => {
    render(<AddSourceDialog open onOpenChange={vi.fn()} />)

    expect(screen.getAllByText(SENTENCE_KEY)).toHaveLength(1)
  })

  it('does not repeat the sentence in the processing step sections', () => {
    function Harness() {
      const { control } = useForm({ defaultValues: { type: 'text', embed: false, async_processing: false } })
      return (
        <ProcessingStep
          control={control as never}
          transformations={[]}
          selectedTransformations={[]}
          onToggleTransformation={vi.fn()}
        />
      )
    }
    render(<Harness />)

    expect(screen.queryAllByText(SENTENCE_KEY)).toHaveLength(0)
  })
})

describe('WizardContainer step indicator', () => {
  it('renders no empty description line for steps that have none', () => {
    const { container } = render(
      <WizardContainer
        currentStep={1}
        steps={[
          { number: 1, title: 'Add Source' },
          { number: 2, title: 'Notebooks' },
          { number: 3, title: 'Process' },
        ]}
      >
        <div>body</div>
      </WizardContainer>,
    )

    expect(screen.getByText('Add Source')).toBeInTheDocument()
    expect(container.querySelectorAll('p.text-xs')).toHaveLength(0)
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./folio.css', () => ({}))

import {
  EvidenceInsert,
  FolioIndex,
  FolioPage,
  FolioState,
} from '..'

describe('Luminous folio primitives', () => {
  it('exposes one named main landmark and associates the page heading', () => {
    render(
      <FolioPage
        eyebrow="Research Core"
        title="A living notebook"
        subtitle="A durable place for connected research."
        margin={<span>Keep this question visible.</span>}
      >
        <p>Notebook content</p>
      </FolioPage>,
    )

    const main = screen.getByRole('main', { name: 'A living notebook' })
    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(main).toHaveAttribute('aria-labelledby')
    expect(screen.getByRole('heading', { name: 'A living notebook' })).toHaveAttribute(
      'id',
      main.getAttribute('aria-labelledby'),
    )
    expect(document.querySelector('[data-dn-folio-margin]')).toBeInTheDocument()
  })

  it('keeps tab selection controlled and moves with arrow keys', () => {
    const onValueChange = vi.fn()
    render(
      <FolioIndex
        label="Notebook sections"
        value="overview"
        onValueChange={onValueChange}
        items={[
          { id: 'overview', label: 'Overview' },
          { id: 'notes', label: 'Notes', badge: <span>3</span> },
          { id: 'graph', label: 'Graph' },
        ]}
      />,
    )

    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(3)
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    expect(tabs[1]).toHaveAttribute('aria-selected', 'false')

    tabs[0].focus()
    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })
    expect(onValueChange).toHaveBeenCalledWith('notes')

    fireEvent.click(tabs[2])
    expect(onValueChange).toHaveBeenCalledWith('graph')
  })

  it('renders every non-content state with its requested recovery action', () => {
    render(
      <div>
        {(['loading', 'empty', 'error'] as const).map(kind => (
          <FolioState
            key={kind}
            kind={kind}
            title={`${kind} state`}
            description={`Description for ${kind}`}
            action={<button type="button">Try again</button>}
          />
        ))}
      </div>,
    )

    expect(screen.getByRole('status', { name: 'loading state' })).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'empty state' })).toBeInTheDocument()
    expect(screen.getByRole('alert', { name: 'error state' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Try again' })).toHaveLength(3)
  })

  it('places an evidence receipt beside content without nesting it in a label', () => {
    render(
      <EvidenceInsert label="Evidence receipt" receipt={<button type="button">Open receipt</button>}>
        <p>Quoted source text</p>
      </EvidenceInsert>,
    )

    expect(screen.getByRole('complementary', { name: 'Evidence receipt' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open receipt' }).closest('label')).toBeNull()
    expect(screen.getByText('Evidence receipt').tagName).not.toBe('LABEL')
  })
})

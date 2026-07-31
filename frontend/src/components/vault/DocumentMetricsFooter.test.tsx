import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DocumentMetricsFooter } from './DocumentMetricsFooter'

describe('DocumentMetricsFooter', () => {
  const labels = {
    words: 'Words',
    characters: 'Characters',
    charactersWithoutWhitespace: 'Characters without spaces',
    readingMinutes: 'Minutes to read',
    selection: 'Selection',
  }

  it('renders document metrics in a polite status region', () => {
    render(
      <DocumentMetricsFooter
        text="hello world"
        selectionText=""
        visible
        labels={labels}
      />,
    )

    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByText('Words: 2')).toBeInTheDocument()
    expect(screen.getByText('Characters: 11')).toBeInTheDocument()
    expect(screen.getByText('Characters without spaces: 10')).toBeInTheDocument()
    expect(screen.getByText('Minutes to read: 1')).toBeInTheDocument()
  })

  it('adds scoped selection metrics only for a non-empty selection', () => {
    render(
      <DocumentMetricsFooter
        text="hello world"
        selectionText="你好世界"
        visible
        labels={labels}
      />,
    )

    expect(screen.getByText('Selection')).toBeInTheDocument()
    const selection = document.querySelector('[data-selection-metrics]')
    expect(selection).not.toBeNull()
    expect(within(selection as HTMLElement).getByText('Words: 2'))
      .toBeInTheDocument()
  })

  it('does not expose metrics while hidden', () => {
    render(
      <DocumentMetricsFooter
        text="hello world"
        selectionText="hello"
        visible={false}
        labels={labels}
      />,
    )

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DocumentMetricsFooter } from './DocumentMetricsFooter'

describe('DocumentMetricsFooter', () => {
  const formatters = {
    words: (count: number) => `${count} words`,
    characters: (count: number) => `${count} characters`,
    readingMinutes: (count: number) => `${count} min read`,
    selectionMetrics: ({ words, characters }: { words: number; characters: number }) => (
      `Selection: ${words} words, ${characters} characters`
    ),
  }

  it('renders document metrics with the exact Task 11 formatter contract', () => {
    render(
      <DocumentMetricsFooter
        text="hello world"
        selectionText=""
        visible
        hasDocument
        formatters={formatters}
        emptyLabel="No document"
      />,
    )

    const footer = screen.getByRole('status')
    expect(Object.keys(formatters).sort()).toEqual([
      'characters',
      'readingMinutes',
      'selectionMetrics',
      'words',
    ])
    expect(footer).toHaveAttribute('aria-live', 'polite')
    expect(footer).toHaveAttribute('tabindex', '0')
    expect(footer).toHaveAccessibleName('2 words, 11 characters, 1 min read')
    footer.focus()
    expect(footer).toHaveFocus()
    expect(screen.getByText('2 words')).toBeInTheDocument()
    expect(screen.getByText('11 characters')).toBeInTheDocument()
    expect(screen.getByText('1 min read')).toBeInTheDocument()
  })

  it('adds scoped selection metrics only for a non-empty selection', () => {
    render(
      <DocumentMetricsFooter
        text="hello world"
        selectionText="你好世界"
        visible
        hasDocument
        formatters={formatters}
        emptyLabel="No document"
      />,
    )

    expect(screen.getByText('Selection: 2 words, 4 characters')).toBeInTheDocument()
    const selection = document.querySelector('[data-selection-metrics]')
    expect(selection).not.toBeNull()
    expect(within(selection as HTMLElement).getByText('Selection: 2 words, 4 characters'))
      .toBeInTheDocument()
    expect(within(selection as HTMLElement).queryByText(/min read/)).not.toBeInTheDocument()
  })

  it('does not expose metrics while hidden', () => {
    render(
      <DocumentMetricsFooter
        text="hello world"
        selectionText="hello"
        visible={false}
        hasDocument
        formatters={formatters}
        emptyLabel="No document"
      />,
    )

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('keeps a no-document footer available for a global graph rootless state', () => {
    render(
      <DocumentMetricsFooter
        text=""
        selectionText=""
        visible
        hasDocument={false}
        formatters={formatters}
        emptyLabel="No document selected"
      />,
    )

    expect(screen.getByRole('status')).toHaveAccessibleName('No document selected')
    expect(screen.getByText('No document selected')).toBeInTheDocument()
  })
})

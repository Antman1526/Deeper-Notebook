import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { VaultEditorBoundary } from './VaultEditorBoundary'

function BrokenEditor(): never {
  throw new Error('editor failed')
}

describe('VaultEditorBoundary', () => {
  it('shows its Reading fallback and resets for another document', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    try {
      const { rerender } = render(
        <VaultEditorBoundary
          resetKey="note:one:source:hash-one"
          fallback={<div aria-label="Plan reading view" />}
        >
          <BrokenEditor />
        </VaultEditorBoundary>,
      )
      expect(screen.getByLabelText('Plan reading view')).toBeInTheDocument()

      rerender(
        <VaultEditorBoundary
          resetKey="note:two:source:hash-two"
          fallback={<div aria-label="Evidence reading view" />}
        >
          <div aria-label="Evidence source" />
        </VaultEditorBoundary>,
      )
      expect(screen.getByLabelText('Evidence source')).toBeInTheDocument()
    } finally {
      consoleError.mockRestore()
    }
  })
})

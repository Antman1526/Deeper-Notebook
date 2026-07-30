import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { act, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { VaultCodeMirror } from '@/components/vault/VaultCodeMirror'

import { OverlaySourceEditor } from './OverlaySourceEditor'

describe('OverlaySourceEditor', () => {
  it('accepts local edits and reports the current document', () => {
    const onChange = vi.fn()
    render(
      <OverlaySourceEditor
        ariaLabel="Research source"
        markdown={'# Research\n'}
        onChange={onChange}
      />,
    )

    const editor = screen.getByRole('textbox', { name: 'Research source' })
    const view = EditorView.findFromDOM(editor)!
    expect(editor).toHaveAttribute('aria-readonly', 'false')
    expect(view.state.facet(EditorState.readOnly)).toBe(false)
    expect(view.state.facet(EditorView.editable)).toBe(true)

    act(() => {
      view.dispatch({
        changes: {
          from: view.state.doc.length,
          insert: 'Changed',
        },
      })
    })

    expect(onChange).toHaveBeenLastCalledWith('# Research\nChanged')
  })

  it('synchronizes external markdown without reporting a local change', () => {
    const onChange = vi.fn()
    const { rerender } = render(
      <OverlaySourceEditor
        ariaLabel="Research source"
        markdown={'# Original\n'}
        onChange={onChange}
      />,
    )

    rerender(
      <OverlaySourceEditor
        ariaLabel="Research source"
        markdown={'# Server update\n'}
        onChange={onChange}
      />,
    )

    const editor = screen.getByRole('textbox', { name: 'Research source' })
    expect(EditorView.findFromDOM(editor)!.state.doc.toString())
      .toBe('# Server update\n')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('temporarily disables editing without weakening the external editor contract', () => {
    const { rerender } = render(
      <OverlaySourceEditor
        ariaLabel="Research source"
        markdown={'# Research\n'}
        onChange={vi.fn()}
        disabled
      />,
    )

    const overlayEditor = screen.getByRole('textbox', { name: 'Research source' })
    expect(overlayEditor).toHaveAttribute('aria-readonly', 'true')
    expect(EditorView.findFromDOM(overlayEditor)!.state.facet(EditorState.readOnly))
      .toBe(true)

    rerender(
      <>
        <OverlaySourceEditor
          ariaLabel="Research source"
          markdown={'# Research\n'}
          onChange={vi.fn()}
        />
        <VaultCodeMirror
          ariaLabel="External source"
          markdown="unchanged"
          extensions={[]}
        />
      </>,
    )

    expect(screen.getByRole('textbox', { name: 'Research source' }))
      .toHaveAttribute('aria-readonly', 'false')
    expect(screen.getByRole('textbox', { name: 'External source' }))
      .toHaveAttribute('aria-readonly', 'true')
  })
})

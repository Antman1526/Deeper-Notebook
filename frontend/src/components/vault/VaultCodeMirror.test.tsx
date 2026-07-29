import { keymap } from '@codemirror/view'
import { EditorState, StateEffect } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { openSearchPanel } from '@codemirror/search'
import { createRef } from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  VaultCodeMirror,
  type VaultCodeMirrorHandle,
} from './VaultCodeMirror'

afterEach(() => vi.restoreAllMocks())

describe('VaultCodeMirror', () => {
  it('exposes exact source while rejecting every mutation path', () => {
    const ref = createRef<VaultCodeMirrorHandle>()
    const mutatingKeymap = keymap.of([{
      key: 'Mod-d',
      run: (view) => {
        view.dispatch({ changes: { from: 0, insert: 'changed' } })
        return true
      },
    }])
    render(
      <VaultCodeMirror
        ref={ref}
        ariaLabel="Plan source"
        markdown={'# Plan\r\n'}
        extensions={[mutatingKeymap]}
      />,
    )

    const editor = screen.getByRole('textbox', { name: 'Plan source' })
    expect(editor).toHaveAttribute('aria-readonly', 'true')
    expect(editor).not.toHaveAttribute('contenteditable', 'true')
    expect(ref.current?.getDocument()).toBe('# Plan\r\n')

    fireEvent(editor, new InputEvent('beforeinput', {
      bubbles: true,
      cancelable: true,
      inputType: 'insertText',
      data: 'changed',
    }))
    fireEvent.paste(editor, {
      clipboardData: { getData: () => 'changed' },
    })
    fireEvent.drop(editor, {
      dataTransfer: { getData: () => 'changed' },
    })
    fireEvent.keyDown(editor, { key: 'd', metaKey: true })

    const view = EditorView.findFromDOM(editor)
    expect(view).not.toBeNull()
    expect(view!.state.facet(EditorState.readOnly)).toBe(true)
    expect(view!.state.facet(EditorView.editable)).toBe(false)
    view!.dispatch({ changes: { from: 0, insert: 'changed' } })
    view!.dispatch({
      changes: { from: 0, insert: 'changed' },
      filter: false,
    })

    expect(ref.current?.getDocument()).toBe('# Plan\r\n')
    expect(view!.state.doc.toString()).toBe('# Plan\n')
  })

  it('offers non-mutating local search and code folding', () => {
    render(
      <VaultCodeMirror
        ariaLabel="Plan source"
        markdown={'# Plan\n\nDetails\n'}
        extensions={[]}
      />,
    )
    const editor = screen.getByRole('textbox', { name: 'Plan source' })
    const view = EditorView.findFromDOM(editor)!
    expect(document.querySelector('.cm-foldGutter')).not.toBeNull()
    expect(openSearchPanel(view)).toBe(true)
    expect(document.querySelector('.cm-search')).not.toBeNull()
    expect(view.state.doc.toString()).toBe('# Plan\n\nDetails\n')
  })

  it('replaces the document when the controlled server snapshot changes', () => {
    const ref = createRef<VaultCodeMirrorHandle>()
    const { rerender } = render(
      <VaultCodeMirror
        ref={ref}
        ariaLabel="Plan source"
        markdown={'# Original\r\n'}
        extensions={[]}
      />,
    )

    rerender(
      <VaultCodeMirror
        ref={ref}
        ariaLabel="Plan source"
        markdown={'# Updated\r\n'}
        extensions={[]}
      />,
    )

    expect(ref.current?.getDocument()).toBe('# Updated\r\n')
    const editor = screen.getByRole('textbox', { name: 'Plan source' })
    expect(EditorView.findFromDOM(editor)!.state.doc.toString()).toBe('# Updated\n')
  })

  it('maps raw CRLF offsets to the exact CodeMirror selection and scroll position', () => {
    const ref = createRef<VaultCodeMirrorHandle>()
    const inertScrollEffect = StateEffect.define<null>()
    const scrollIntoView = vi.spyOn(EditorView, 'scrollIntoView')
      .mockImplementation(() => inertScrollEffect.of(null))
    const { rerender } = render(
      <VaultCodeMirror
        ref={ref}
        ariaLabel="Plan source"
        markdown={'# Original\n\n## Target\n'}
        extensions={[]}
      />,
    )
    const updatedSource = '# Updated\r\n\r\nParagraph\r\n\r\n## Target\r\n'

    rerender(
      <VaultCodeMirror
        ref={ref}
        ariaLabel="Plan source"
        markdown={updatedSource}
        extensions={[]}
      />,
    )

    const editor = screen.getByRole('textbox', { name: 'Plan source' })
    const view = EditorView.findFromDOM(editor)!
    const expectedOffset = view.state.doc.toString().indexOf('## Target')
    act(() => ref.current?.scrollToOffset(updatedSource.indexOf('## Target')))

    expect(view.state.selection.main.anchor).toBe(expectedOffset)
    expect(scrollIntoView).toHaveBeenCalledWith(expectedOffset, { y: 'center' })
  })
})

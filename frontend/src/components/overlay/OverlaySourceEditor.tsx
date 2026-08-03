'use client'

import { useLayoutEffect, useMemo, useRef } from 'react'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { markdown } from '@codemirror/lang-markdown'
import {
  defaultHighlightStyle,
  foldGutter,
  foldKeymap,
  syntaxHighlighting,
} from '@codemirror/language'
import { findNext, findPrevious, openSearchPanel } from '@codemirror/search'
import { Annotation, Compartment, EditorState } from '@codemirror/state'
import {
  drawSelection,
  EditorView,
  highlightActiveLine,
  keymap,
  lineNumbers,
} from '@codemirror/view'

export interface OverlaySourceEditorProps {
  ariaLabel: string
  markdown: string
  onChange: (markdown: string) => void
  disabled?: boolean
  onSelectionChange?: (from: number, to: number) => void
}

const externalUpdate = Annotation.define<boolean>()

function editorStateExtensions(
  ariaLabel: string,
  disabled: boolean,
) {
  return [
    EditorState.readOnly.of(disabled),
    EditorView.editable.of(!disabled),
    EditorView.contentAttributes.of({
      role: 'textbox',
      'aria-label': ariaLabel,
      'aria-multiline': 'true',
      'aria-readonly': disabled ? 'true' : 'false',
      ...(disabled ? { 'aria-disabled': 'true' } : {}),
    }),
  ]
}

export function OverlaySourceEditor({
  ariaLabel,
  markdown: source,
  onChange,
  disabled = false,
  onSelectionChange,
}: OverlaySourceEditorProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)
  const onChangeRef = useRef(onChange)
  const onSelectionChangeRef = useRef(onSelectionChange)
  const stateCompartment = useMemo(() => new Compartment(), [])

  useLayoutEffect(() => {
    onChangeRef.current = onChange
    onSelectionChangeRef.current = onSelectionChange
  }, [onChange, onSelectionChange])

  useLayoutEffect(() => {
    const host = hostRef.current
    if (!host) return

    const view = new EditorView({
      state: EditorState.create({
        doc: source,
        extensions: [
          stateCompartment.of(editorStateExtensions(ariaLabel, disabled)),
          lineNumbers(),
          foldGutter(),
          highlightActiveLine(),
          drawSelection(),
          syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
          markdown(),
          history(),
          keymap.of([
            ...defaultKeymap,
            ...historyKeymap,
            { key: 'Mod-f', run: openSearchPanel },
            { key: 'F3', run: findNext },
            { key: 'Shift-F3', run: findPrevious },
            ...foldKeymap,
          ]),
          EditorView.updateListener.of((update) => {
            if (update.selectionSet) {
              const selection = update.state.selection.main
              onSelectionChangeRef.current?.(selection.from, selection.to)
            }
            if (
              update.docChanged
              && !update.transactions.some(
                (transaction) => transaction.annotation(externalUpdate),
              )
            ) {
              onChangeRef.current(update.state.doc.toString())
            }
          }),
        ],
      }),
      parent: host,
    })
    viewRef.current = view

    return () => {
      view.destroy()
      if (viewRef.current === view) viewRef.current = null
    }
    // CodeMirror is created once; controlled inputs are synchronized below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateCompartment])

  useLayoutEffect(() => {
    const view = viewRef.current
    if (!view || view.state.doc.toString() === source.replace(/\r\n?/g, '\n')) {
      return
    }
    view.dispatch({
      changes: {
        from: 0,
        to: view.state.doc.length,
        insert: source,
      },
      annotations: externalUpdate.of(true),
      filter: false,
    })
  }, [source])

  useLayoutEffect(() => {
    const view = viewRef.current
    if (!view) return
    view.dispatch({
      effects: stateCompartment.reconfigure(
        editorStateExtensions(ariaLabel, disabled),
      ),
      filter: false,
    })
  }, [ariaLabel, disabled, stateCompartment])

  return (
    <div
      ref={hostRef}
      className="dn-vault-editor dn-overlay-editor"
      data-disabled={disabled ? 'true' : 'false'}
    />
  )
}

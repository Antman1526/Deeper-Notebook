'use client'

import {
  forwardRef,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
} from 'react'
import { markdown } from '@codemirror/lang-markdown'
import {
  defaultHighlightStyle,
  foldGutter,
  foldKeymap,
  syntaxHighlighting,
} from '@codemirror/language'
import { findNext, findPrevious, openSearchPanel } from '@codemirror/search'
import {
  Annotation,
  EditorState,
  Prec,
  type Extension,
} from '@codemirror/state'
import {
  drawSelection,
  EditorView,
  highlightActiveLine,
  keymap,
  lineNumbers,
} from '@codemirror/view'

export interface VaultCodeMirrorHandle {
  getDocument: () => string
  scrollToOffset: (offset: number) => void
}

export interface VaultCodeMirrorProps {
  ariaLabel: string
  markdown: string
  extensions: Extension[]
  className?: string
}

const externalUpdate = Annotation.define<boolean>()

const rejectDocumentChanges = EditorState.transactionFilter.of(
  (transaction) => transaction.docChanged && !transaction.annotation(externalUpdate)
    ? []
    : transaction,
)

const lockedExtensions: Extension[] = [
  EditorState.readOnly.of(true),
  EditorView.editable.of(false),
  EditorView.contentAttributes.of({
    role: 'textbox',
    'aria-multiline': 'true',
    'aria-readonly': 'true',
  }),
  lineNumbers(),
  foldGutter(),
  highlightActiveLine(),
  drawSelection(),
  syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
  markdown(),
  keymap.of([
    { key: 'Mod-f', run: openSearchPanel },
    { key: 'F3', run: findNext },
    { key: 'Shift-F3', run: findPrevious },
    ...foldKeymap,
  ]),
]

export const VaultCodeMirror = forwardRef<
  VaultCodeMirrorHandle,
  VaultCodeMirrorProps
>(function VaultCodeMirror({ ariaLabel, markdown: source, extensions, className }, ref) {
  const hostRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)
  const sourceRef = useRef(source)
  const initialExtensionsRef = useRef(extensions)
  const initialAriaLabelRef = useRef(ariaLabel)

  useImperativeHandle(ref, () => ({
    getDocument: () => sourceRef.current,
    scrollToOffset: (offset) => {
      const view = viewRef.current
      if (!view) return
      const position = Math.max(0, Math.min(offset, view.state.doc.length))
      view.dispatch({
        selection: { anchor: position },
        effects: EditorView.scrollIntoView(position, { y: 'center' }),
      })
    },
  }), [])

  useLayoutEffect(() => {
    const host = hostRef.current
    if (!host) return

    const view = new EditorView({
      state: EditorState.create({
        doc: sourceRef.current,
        extensions: [
          Prec.highest([rejectDocumentChanges, ...lockedExtensions]),
          initialExtensionsRef.current,
          EditorView.contentAttributes.of({ 'aria-label': initialAriaLabelRef.current }),
        ],
      }),
      dispatchTransactions: (transactions, editor) => {
        editor.update(transactions.filter(
          (transaction) => !transaction.docChanged
            || Boolean(transaction.annotation(externalUpdate)),
        ))
      },
      parent: host,
    })
    viewRef.current = view

    return () => {
      view.destroy()
      if (viewRef.current === view) viewRef.current = null
    }
  }, [])

  useLayoutEffect(() => {
    const view = viewRef.current
    if (!view || sourceRef.current === source) return

    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: source },
      annotations: externalUpdate.of(true),
    })
    sourceRef.current = source
  }, [source])

  return <div ref={hostRef} className={['dn-vault-editor', className].filter(Boolean).join(' ')} />
})

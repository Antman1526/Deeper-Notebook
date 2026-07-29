'use client'

import {
  forwardRef,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
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
  Compartment,
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

function collectCrlfCarriageReturns(source: string): number[] {
  const positions: number[] = []
  for (
    let position = source.indexOf('\r\n');
    position >= 0;
    position = source.indexOf('\r\n', position + 2)
  ) {
    positions.push(position)
  }
  return positions
}

function countPositionsBefore(positions: readonly number[], offset: number): number {
  let start = 0
  let end = positions.length
  while (start < end) {
    const middle = start + Math.floor((end - start) / 2)
    if (positions[middle] < offset) start = middle + 1
    else end = middle
  }
  return start
}

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
  const crlfCarriageReturns = useMemo(
    () => collectCrlfCarriageReturns(source),
    [source],
  )
  const ariaLabelCompartment = useMemo(() => new Compartment(), [])
  const callerExtensionsCompartment = useMemo(() => new Compartment(), [])
  const hostRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)
  const sourceRef = useRef(source)
  const crlfCarriageReturnsRef = useRef(crlfCarriageReturns)
  const configuredExtensionsRef = useRef(extensions)
  const configuredAriaLabelRef = useRef(ariaLabel)

  useImperativeHandle(ref, () => ({
    getDocument: () => sourceRef.current,
    scrollToOffset: (offset) => {
      const view = viewRef.current
      if (!view) return
      const rawPosition = Math.max(0, Math.min(offset, sourceRef.current.length))
      const position = rawPosition - countPositionsBefore(
        crlfCarriageReturnsRef.current,
        rawPosition,
      )
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
          Prec.highest([
            rejectDocumentChanges,
            ...lockedExtensions,
            ariaLabelCompartment.of(EditorView.contentAttributes.of({
              'aria-label': configuredAriaLabelRef.current,
            })),
          ]),
          callerExtensionsCompartment.of(configuredExtensionsRef.current),
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
  }, [ariaLabelCompartment, callerExtensionsCompartment])

  useLayoutEffect(() => {
    const view = viewRef.current
    if (!view || sourceRef.current === source) return

    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: source },
      annotations: externalUpdate.of(true),
      filter: false,
    })
    sourceRef.current = source
    crlfCarriageReturnsRef.current = crlfCarriageReturns
  }, [crlfCarriageReturns, source])

  useLayoutEffect(() => {
    const view = viewRef.current
    if (!view) return

    const effects = []
    if (configuredAriaLabelRef.current !== ariaLabel) {
      effects.push(ariaLabelCompartment.reconfigure(
        EditorView.contentAttributes.of({ 'aria-label': ariaLabel }),
      ))
    }
    if (configuredExtensionsRef.current !== extensions) {
      effects.push(callerExtensionsCompartment.reconfigure(extensions))
    }
    if (effects.length === 0) return

    view.dispatch({ effects, filter: false })
    configuredAriaLabelRef.current = ariaLabel
    configuredExtensionsRef.current = extensions
  }, [ariaLabel, ariaLabelCompartment, callerExtensionsCompartment, extensions])

  return <div ref={hostRef} className={['dn-vault-editor', className].filter(Boolean).join(' ')} />
})

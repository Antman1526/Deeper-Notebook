import { Fragment, type ReactNode } from 'react'

// v0.8.130 — renders a translated sentence that contains inline markup, so a locale
// can put a link, a key or a code value wherever its grammar needs it:
//   "Tip: hit <key/> from anywhere…"       → <key/> is filled by components.key()
//   "…available on the <link>Study home</link>." → components.link(children)
// Splitting such sentences into "lead" and "tail" keys forced every language into
// English word order. Unknown tags keep their inner text; malformed markup is shown
// as written, so a translation mistake never drops words.

export type RichTextComponents = Record<string, (children: ReactNode) => ReactNode>

const TAG = /<([a-zA-Z][\w-]*)\s*\/>|<([a-zA-Z][\w-]*)>([\s\S]*?)<\/\2>/g

export function RichText({ text, components = {} }: { text: string; components?: RichTextComponents }) {
  const parts: ReactNode[] = []
  let last = 0
  for (const match of text.matchAll(TAG)) {
    const index = match.index ?? 0
    if (index > last) parts.push(text.slice(last, index))
    const [, selfClosing, open, inner] = match
    const name = selfClosing ?? open
    const render = components[name]
    const children = selfClosing ? null : inner
    parts.push(<Fragment key={index}>{render ? render(children) : children}</Fragment>)
    last = index + match[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <>{parts}</>
}

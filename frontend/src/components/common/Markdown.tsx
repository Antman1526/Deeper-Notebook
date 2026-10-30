'use client'

import React from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'

const defaultTableComponents: Components = {
  table: ({ children }) => (
    <div className="my-4 overflow-x-auto">
      <table className="min-w-full border-collapse border border-border">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted">{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr className="border-b border-border">{children}</tr>,
  th: ({ children }) => (
    <th className="border border-border px-3 py-2 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border px-3 py-2">{children}</td>,
}

export interface MarkdownProps {
  children?: string
  content?: string
  className?: string
  components?: Components
}

export function Markdown({ children, content: contentProp, className, components }: MarkdownProps) {
  const mergedComponents = components
    ? { ...defaultTableComponents, ...components }
    : defaultTableComponents

  const content = (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={mergedComponents}
    >
      {children ?? contentProp ?? ""}
    </ReactMarkdown>
  )

  return className ? <div className={className}>{content}</div> : content
}

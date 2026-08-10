import type { ReactNode } from 'react'

import { FolioRouteFrame } from '../folio/FolioRouteFrame'

export const knowledgeRouteFolioMetadata = {
  '/sources': { title: 'Sources', eyebrow: 'Collect' },
  '/capture': { title: 'Capture', eyebrow: 'Collect' },
  '/notebooks': { title: 'Notebooks', eyebrow: 'Organize' },
  '/search': { title: 'Ask & Search', eyebrow: 'Discover' },
  '/study': { title: 'Study', eyebrow: 'Discover' },
} as const

export type KnowledgeRoutePath = keyof typeof knowledgeRouteFolioMetadata

export function KnowledgeRouteFrame({
  route,
  children,
  actions,
  description,
  context,
}: {
  route: KnowledgeRoutePath
  children: ReactNode
  actions?: ReactNode
  description?: string
  context?: ReactNode
}) {
  const metadata = knowledgeRouteFolioMetadata[route]
  return (
    <FolioRouteFrame
      section={metadata.eyebrow}
      title={metadata.title}
      description={description}
      actions={actions}
      context={context}
    >
      {children}
    </FolioRouteFrame>
  )
}

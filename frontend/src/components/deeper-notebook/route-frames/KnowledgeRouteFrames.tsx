import type { ReactNode } from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'

import { FolioRouteFrame } from '../folio/FolioRouteFrame'

export const knowledgeRouteFolioMetadata = {
  '/sources': { titleKey: 'navigation.sources', eyebrowKey: 'navigation.collect' },
  '/capture': { titleKey: 'knowledge.knowledgeRouteFrames.capture', eyebrowKey: 'navigation.collect' },
  '/notebooks': { titleKey: 'navigation.notebooks', eyebrowKey: 'knowledge.knowledgeRouteFrames.organize' },
  '/search': { titleKey: 'knowledge.knowledgeRouteFrames.askAndSearch', eyebrowKey: 'knowledge.knowledgeRouteFrames.discover' },
  '/study': { titleKey: 'navigation.study', eyebrowKey: 'knowledge.knowledgeRouteFrames.discover' },
} as const

export type KnowledgeRoutePath = keyof typeof knowledgeRouteFolioMetadata

export function KnowledgeRouteFrame({
  route,
  children,
  actions,
  description,
  context,
  title,
}: {
  route: KnowledgeRoutePath
  children: ReactNode
  actions?: ReactNode
  description?: string
  context?: ReactNode
  title?: string
}) {
  const { t } = useTranslation()
  const metadata = knowledgeRouteFolioMetadata[route]
  return (
    <FolioRouteFrame
      section={t(metadata.eyebrowKey)}
      title={title ?? t(metadata.titleKey)}
      description={description}
      actions={actions}
      context={context}
    >
      {children}
    </FolioRouteFrame>
  )
}

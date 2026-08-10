import type { ReactNode } from 'react'

import { FolioRouteFrame } from '../folio/FolioRouteFrame'

export const systemRouteFolioMetadata = {
  '/podcasts': { title: 'Podcasts', eyebrow: 'Create' },
  '/transformations': { title: 'Transformations', eyebrow: 'Create' },
  '/settings': { title: 'Settings', eyebrow: 'Manage' },
  '/settings/api-keys': { title: 'API keys', eyebrow: 'Manage' },
  '/settings/local-models': { title: 'Local models', eyebrow: 'Manage' },
  '/settings/mcp': { title: 'Integrations', eyebrow: 'Manage' },
  '/settings/launcher-prefs': { title: 'Launcher preferences', eyebrow: 'Manage' },
  '/advanced': { title: 'Advanced tools', eyebrow: 'Manage' },
  '/setup-wizard': { title: 'Setup', eyebrow: 'Setup' },
} as const

export type SystemRoutePath = keyof typeof systemRouteFolioMetadata

export function SystemRouteFrame({
  route,
  children,
  actions,
  description,
  context,
}: {
  route: SystemRoutePath
  children: ReactNode
  actions?: ReactNode
  description?: string
  context?: ReactNode
}) {
  const metadata = systemRouteFolioMetadata[route]
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

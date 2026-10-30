import type { ReactNode } from 'react'

import { useTranslation } from '@/lib/hooks/use-translation'

import { FolioRouteFrame } from '../folio/FolioRouteFrame'

export const systemRouteFolioMetadata = {
  '/podcasts': { titleKey: 'workspace.systemRouteFrames.titlePodcasts', eyebrowKey: 'workspace.systemRouteFrames.eyebrowCreate' },
  '/transformations': { titleKey: 'workspace.systemRouteFrames.titleTransformations', eyebrowKey: 'workspace.systemRouteFrames.eyebrowCreate' },
  '/settings': { titleKey: 'workspace.systemRouteFrames.titleSettings', eyebrowKey: 'workspace.systemRouteFrames.eyebrowManage' },
  '/settings/api-keys': { titleKey: 'workspace.systemRouteFrames.titleApiKeys', eyebrowKey: 'workspace.systemRouteFrames.eyebrowManage' },
  '/settings/local-models': { titleKey: 'workspace.systemRouteFrames.titleLocalModels', eyebrowKey: 'workspace.systemRouteFrames.eyebrowManage' },
  '/settings/mcp': { titleKey: 'workspace.systemRouteFrames.titleIntegrations', eyebrowKey: 'workspace.systemRouteFrames.eyebrowManage' },
  '/settings/launcher-prefs': { titleKey: 'workspace.systemRouteFrames.titleLauncherPreferences', eyebrowKey: 'workspace.systemRouteFrames.eyebrowManage' },
  '/advanced': { titleKey: 'workspace.systemRouteFrames.titleAdvancedTools', eyebrowKey: 'workspace.systemRouteFrames.eyebrowManage' },
  '/setup-wizard': { titleKey: 'workspace.systemRouteFrames.titleSetup', eyebrowKey: 'workspace.systemRouteFrames.eyebrowSetup' },
} as const

export type SystemRoutePath = keyof typeof systemRouteFolioMetadata

export function SystemRouteFrame({
  route,
  children,
  actions,
  description,
  context,
  title,
}: {
  route: SystemRoutePath
  children: ReactNode
  actions?: ReactNode
  description?: string
  context?: ReactNode
  title?: string
}) {
  const { t } = useTranslation()
  const metadata = systemRouteFolioMetadata[route]
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

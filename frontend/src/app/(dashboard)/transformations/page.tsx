'use client'

import { useState } from 'react'
import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DefaultPromptEditor } from './components/DefaultPromptEditor'
import { TransformationsList } from './components/TransformationsList'
import { TransformationPlayground } from './components/TransformationPlayground'
import { useTransformations } from '@/lib/hooks/use-transformations'
import { Transformation } from '@/lib/types/transformations'
import { Wand2, Play, RefreshCw } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'
import { SystemRouteFrame } from '@/components/deeper-notebook/route-frames/SystemRouteFrames'

export default function TransformationsPage() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState('transformations')
  const [selectedTransformation, setSelectedTransformation] = useState<Transformation | undefined>()
  const { data: transformations, isLoading, refetch } = useTransformations()

  const handlePlayground = (transformation: Transformation) => {
    setSelectedTransformation(transformation)
    setActiveTab('playground')
  }

  return (
    <AppShell>
      <SystemRouteFrame
        route="/transformations"
        description={t('transformations.desc')}
        actions={
          <Button variant="outline" size="sm" aria-label="Refresh transformations" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        }
      >
        <div className="space-y-6">
          {/* v0.7.164 — Header reorganized. The previous JSX opened
              a `flex items-center justify-between` shell that had
              only a left-half (the right slot was empty, so
              justify-between did no work) and the description sat
              in a separate `max-w-5xl` block below with no top
              margin — read as orphaned. Replaced with a single
              `<header>` stack: title + refresh on top row,
              description below with `space-y-2` rhythm. H1
              promoted from `text-2xl font-bold` to the v0.7.153
              standard `text-3xl font-semibold tracking-tight` so
              all dashboard page titles weigh the same. */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t('transformations.workspace')}</p>
            <TabsList aria-label={t('common.accessibility.transformationViews')} className="w-full max-w-xl">
              <TabsTrigger value="transformations" className="flex items-center gap-2">
                <Wand2 className="h-4 w-4" />
                {t('transformations.title')}
              </TabsTrigger>
              <TabsTrigger value="playground" className="flex items-center gap-2">
                <Play className="h-4 w-4" />
                {t('transformations.playground')}
              </TabsTrigger>
            </TabsList>
          </div>
          
          <TabsContent value="transformations" className="space-y-6">
            <DefaultPromptEditor />
            <TransformationsList 
              transformations={transformations} 
              isLoading={isLoading}
              onPlayground={handlePlayground}
            />
          </TabsContent>
          
          <TabsContent value="playground">
            <TransformationPlayground 
              transformations={transformations}
              selectedTransformation={selectedTransformation}
            />
          </TabsContent>
        </Tabs>
        </div>
      </SystemRouteFrame>
    </AppShell>
  )
}

'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ModelRoutePlanPanel } from '@/components/local-models/ModelRoutePlanPanel'
import { useLocalModelSettings, useLocalModelsHealth, useModelRoutePlan } from '@/lib/hooks/use-local-models'
import { useModelDefaults, useModels } from '@/lib/hooks/use-models'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  getLocalResearchReadinessReason,
  getResearchModeAvailability,
} from '@/lib/knowledge/research-modes'

interface KnowledgeAskPaneProps {
  selectedDocumentIds: string[]
  readinessReason?: string | null
}

export function KnowledgeAskPane({
  selectedDocumentIds,
  readinessReason = null,
}: KnowledgeAskPaneProps) {
  const { t } = useTranslation()
  const [question, setQuestion] = useState('')
  const localModelsHealth = useLocalModelsHealth()
  const { data: modelDefaults } = useModelDefaults()
  const { data: models } = useModels()
  const defaultChatModel = models?.find(
    (model) => model.id === modelDefaults?.default_chat_model && model.type === 'language',
  ) ?? null
  const localReadinessReason = getLocalResearchReadinessReason(
    localModelsHealth,
    defaultChatModel
      ? { id: defaultChatModel.id, credentialId: defaultChatModel.credential ?? null }
      : null,
    t,
  )
  const selectionLabel = t(
    selectedDocumentIds.length === 1
      ? 'knowledge.knowledgeAskPane.selectedDocumentOne'
      : 'knowledge.knowledgeAskPane.selectedDocumentOther',
    { count: selectedDocumentIds.length },
  )
  const readiness = getResearchModeAvailability('ask', {
    target: { kind: 'ask' },
    askReadinessReason: readinessReason ?? localReadinessReason,
    t,
  })
  const settings = useLocalModelSettings()
  const researchRoute = useModelRoutePlan(settings.data ? {
    role: 'research_chat', execution_policy: settings.data.execution_policy, compute_profile: settings.data.compute_profile,
    role_override_model_id: settings.data.role_overrides.research_chat ?? null, modalities: ['text'],
  } : null)
  const scopeReason = selectedDocumentIds.length > 0
    ? t('knowledge.knowledgeAskPane.scopedUnavailable')
    : t('knowledge.knowledgeAskPane.selectDocuments')

  return (
    <section aria-label={t('knowledge.knowledgeAskPane.region')} className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">{t('knowledge.knowledgeAskPane.title')}</h2>
        <p className="text-sm text-muted-foreground">{selectionLabel}</p>
      </div>
      {readiness.reason && <p role="status" className="text-sm text-muted-foreground">{readiness.reason}</p>}
      <ModelRoutePlanPanel routeId="research-chat-route" title={t('knowledge.knowledgeAskPane.researchChatRoute')} plan={researchRoute.data} isError={settings.isError || researchRoute.isError} isLoading={settings.isLoading || researchRoute.isLoading} />
      <p className="text-sm text-muted-foreground">{scopeReason}</p>
      <Textarea
        aria-label={t('knowledge.knowledgeAskPane.questionLabel')}
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        placeholder={t('knowledge.knowledgeAskPane.questionPlaceholder')}
      />
      <Button type="button" disabled>
        {t('knowledge.knowledgeAskPane.askSelected')}
      </Button>
    </section>
  )
}

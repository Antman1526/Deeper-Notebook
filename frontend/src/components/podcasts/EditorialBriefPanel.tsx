'use client'

import { useTranslation } from '@/lib/hooks/use-translation'

export type EditorialAudience = 'foundation' | 'practitioner' | 'expert'
export type EditorialPurpose = 'explain' | 'analyze' | 'challenge' | 'compare' | 'teach'
export type EditorialFormat = 'brief' | 'deep_dive' | 'critique' | 'debate'
export type EditorialEvidencePolicy = 'strict' | 'interpretation'

export interface EditorialBriefValues {
  centralQuestion: string
  audience: EditorialAudience
  purpose: EditorialPurpose
  format: EditorialFormat
  targetMinutes: number
  requiredTakeaway: string
  includeUnansweredQuestions: boolean
  evidencePolicy: EditorialEvidencePolicy
  episodeProfileName: string
  speakerProfileName: string
}
export interface EditorialBriefPanelProps {
  value: EditorialBriefValues
  onChange: (patch: Partial<EditorialBriefValues>) => void
  episodeProfiles?: string[]
  speakerProfiles?: string[]
}

export function EditorialBriefPanel({ value, onChange, episodeProfiles = [], speakerProfiles = [] }: EditorialBriefPanelProps) {
  const { t } = useTranslation()
  return (
    <section data-studio-region="editorial-brief" data-region="editorial-brief" aria-label={t('podcasts.editorialBriefPanel.title')} className="space-y-3 rounded-md border p-4">
      <header>
        <h3 className="font-semibold">{t('podcasts.editorialBriefPanel.title')}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('podcasts.editorialBriefPanel.localNotice')}</p>
      </header>
      <label className="grid gap-1 text-sm" htmlFor="podcast-central-question">{t('podcasts.editorialBriefPanel.centralQuestion')}
        <textarea id="podcast-central-question" value={value.centralQuestion} onChange={(event) => onChange({ centralQuestion: event.target.value })} className="min-h-20 rounded-md border bg-background p-2" />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm" htmlFor="podcast-audience">{t('podcasts.editorialBriefPanel.audience')}
          <select id="podcast-audience" value={value.audience} onChange={(event) => onChange({ audience: event.target.value as EditorialAudience })} className="h-9 rounded-md border bg-background px-2">
            <option value="foundation">{t('podcasts.editorialBriefPanel.audienceFoundation')}</option><option value="practitioner">{t('podcasts.editorialBriefPanel.audiencePractitioner')}</option><option value="expert">{t('podcasts.editorialBriefPanel.audienceExpert')}</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm" htmlFor="podcast-purpose">{t('podcasts.editorialBriefPanel.purpose')}
          <select id="podcast-purpose" value={value.purpose} onChange={(event) => onChange({ purpose: event.target.value as EditorialPurpose })} className="h-9 rounded-md border bg-background px-2">
            <option value="explain">{t('podcasts.editorialBriefPanel.purposeExplain')}</option><option value="analyze">{t('podcasts.editorialBriefPanel.purposeAnalyze')}</option><option value="challenge">{t('podcasts.editorialBriefPanel.purposeChallenge')}</option><option value="compare">{t('podcasts.editorialBriefPanel.purposeCompare')}</option><option value="teach">{t('podcasts.editorialBriefPanel.purposeTeach')}</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm" htmlFor="podcast-format">{t('podcasts.editorialBriefPanel.format')}
          <select id="podcast-format" value={value.format} onChange={(event) => onChange({ format: event.target.value as EditorialFormat })} className="h-9 rounded-md border bg-background px-2">
            <option value="brief">{t('podcasts.editorialBriefPanel.formatBrief')}</option><option value="deep_dive">{t('podcasts.editorialBriefPanel.formatDeepDive')}</option><option value="critique">{t('podcasts.editorialBriefPanel.formatCritique')}</option><option value="debate">{t('podcasts.editorialBriefPanel.formatDebate')}</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm" htmlFor="podcast-target-minutes">{t('podcasts.editorialBriefPanel.targetMinutes')}
          <input id="podcast-target-minutes" type="number" min={1} max={180} value={value.targetMinutes} onChange={(event) => onChange({ targetMinutes: Math.max(1, Number(event.target.value) || 1) })} className="h-9 rounded-md border bg-background px-2" />
        </label>
      </div>
      <label className="grid gap-1 text-sm" htmlFor="podcast-required-takeaway">{t('podcasts.editorialBriefPanel.requiredTakeaway')}
        <textarea id="podcast-required-takeaway" value={value.requiredTakeaway} onChange={(event) => onChange({ requiredTakeaway: event.target.value })} className="min-h-16 rounded-md border bg-background p-2" />
      </label>
      <label className="flex items-center gap-2 text-sm" htmlFor="podcast-unanswered-questions">
        <input id="podcast-unanswered-questions" type="checkbox" checked={value.includeUnansweredQuestions} onChange={(event) => onChange({ includeUnansweredQuestions: event.target.checked })} />
        {t('podcasts.editorialBriefPanel.includeUnanswered')}
      </label>
      <label className="grid gap-1 text-sm" htmlFor="podcast-evidence-policy">{t('podcasts.editorialBriefPanel.evidencePolicy')}
        <select id="podcast-evidence-policy" value={value.evidencePolicy} onChange={(event) => onChange({ evidencePolicy: event.target.value as EditorialEvidencePolicy })} className="h-9 rounded-md border bg-background px-2">
          <option value="strict">{t('podcasts.editorialBriefPanel.evidenceStrict')}</option><option value="interpretation">{t('podcasts.editorialBriefPanel.evidenceInterpretation')}</option>
        </select>
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm" htmlFor="podcast-episode-profile">{t('podcasts.editorialBriefPanel.episodeProfile')}
          <select id="podcast-episode-profile" value={value.episodeProfileName} onChange={(event) => onChange({ episodeProfileName: event.target.value })} className="h-9 rounded-md border bg-background px-2">
            <option value="">{t('podcasts.editorialBriefPanel.chooseProfile')}</option>{episodeProfiles.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-sm" htmlFor="podcast-speaker-profile">{t('podcasts.editorialBriefPanel.speakerProfile')}
          <select id="podcast-speaker-profile" value={value.speakerProfileName} onChange={(event) => onChange({ speakerProfileName: event.target.value })} className="h-9 rounded-md border bg-background px-2">
            <option value="">{t('podcasts.editorialBriefPanel.chooseProfile')}</option>{speakerProfiles.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
      </div>
    </section>
  )
}

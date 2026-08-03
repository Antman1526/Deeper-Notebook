'use client'

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
  return (
    <section data-studio-region="editorial-brief" data-region="editorial-brief" aria-label="Editorial Brief" className="space-y-3 rounded-md border p-4">
      <header>
        <h3 className="font-semibold">Editorial Brief</h3>
        <p className="mt-1 text-sm text-muted-foreground">All brief edits stay local until production confirmation.</p>
      </header>
      <label className="grid gap-1 text-sm" htmlFor="podcast-central-question">Central question
        <textarea id="podcast-central-question" value={value.centralQuestion} onChange={(event) => onChange({ centralQuestion: event.target.value })} className="min-h-20 rounded-md border bg-background p-2" />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm" htmlFor="podcast-audience">Audience
          <select id="podcast-audience" value={value.audience} onChange={(event) => onChange({ audience: event.target.value as EditorialAudience })} className="h-9 rounded-md border bg-background px-2">
            <option value="foundation">Foundation</option><option value="practitioner">Practitioner</option><option value="expert">Expert</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm" htmlFor="podcast-purpose">Purpose
          <select id="podcast-purpose" value={value.purpose} onChange={(event) => onChange({ purpose: event.target.value as EditorialPurpose })} className="h-9 rounded-md border bg-background px-2">
            <option value="explain">Explain</option><option value="analyze">Analyze</option><option value="challenge">Challenge</option><option value="compare">Compare</option><option value="teach">Teach</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm" htmlFor="podcast-format">Format
          <select id="podcast-format" value={value.format} onChange={(event) => onChange({ format: event.target.value as EditorialFormat })} className="h-9 rounded-md border bg-background px-2">
            <option value="brief">Brief</option><option value="deep_dive">Deep dive</option><option value="critique">Critique</option><option value="debate">Debate</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm" htmlFor="podcast-target-minutes">Target minutes
          <input id="podcast-target-minutes" type="number" min={1} max={180} value={value.targetMinutes} onChange={(event) => onChange({ targetMinutes: Math.max(1, Number(event.target.value) || 1) })} className="h-9 rounded-md border bg-background px-2" />
        </label>
      </div>
      <label className="grid gap-1 text-sm" htmlFor="podcast-required-takeaway">Required takeaway
        <textarea id="podcast-required-takeaway" value={value.requiredTakeaway} onChange={(event) => onChange({ requiredTakeaway: event.target.value })} className="min-h-16 rounded-md border bg-background p-2" />
      </label>
      <label className="flex items-center gap-2 text-sm" htmlFor="podcast-unanswered-questions">
        <input id="podcast-unanswered-questions" type="checkbox" checked={value.includeUnansweredQuestions} onChange={(event) => onChange({ includeUnansweredQuestions: event.target.checked })} />
        Include unanswered questions
      </label>
      <label className="grid gap-1 text-sm" htmlFor="podcast-evidence-policy">Evidence policy
        <select id="podcast-evidence-policy" value={value.evidencePolicy} onChange={(event) => onChange({ evidencePolicy: event.target.value as EditorialEvidencePolicy })} className="h-9 rounded-md border bg-background px-2">
          <option value="strict">Strict</option><option value="interpretation">Interpretation</option>
        </select>
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm" htmlFor="podcast-episode-profile">Episode profile
          <select id="podcast-episode-profile" value={value.episodeProfileName} onChange={(event) => onChange({ episodeProfileName: event.target.value })} className="h-9 rounded-md border bg-background px-2">
            <option value="">Choose a profile</option>{episodeProfiles.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-sm" htmlFor="podcast-speaker-profile">Speaker profile
          <select id="podcast-speaker-profile" value={value.speakerProfileName} onChange={(event) => onChange({ speakerProfileName: event.target.value })} className="h-9 rounded-md border bg-background px-2">
            <option value="">Choose a profile</option>{speakerProfiles.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
      </div>
    </section>
  )
}

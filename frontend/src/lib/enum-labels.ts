// Translated labels for API enum values that are rendered as text.
//
// Each map pairs a known wire value with its locale key. Values that are not
// listed (a newer backend, an open-ended string) fall back to the raw text, so
// an unexpected value never renders as a missing key.

type Translate = (key: string, options?: Record<string, unknown>) => string

export type EnumLabelKeys = Readonly<Record<string, string>>

export function enumLabel(t: Translate, keys: EnumLabelKeys, value: string, fallback: string = value): string {
  return Object.prototype.hasOwnProperty.call(keys, value) ? t(keys[value]) : fallback
}

/** `analyzing_sources` -> `analyzing sources`, the fallback for an unknown value. */
export function spacedEnum(value: string): string {
  return value.replace(/_/g, ' ')
}

export const STUDY_PLAN_STATE_KEYS: EnumLabelKeys = {
  draft: 'study.planStates.draft',
  analyzing_sources: 'study.planStates.analyzingSources',
  syllabus_proposed: 'study.planStates.syllabusProposed',
  editing: 'study.planStates.editing',
  approved: 'study.planStates.approved',
  generating: 'study.planStates.generating',
  active: 'study.planStates.active',
  completed: 'study.planStates.completed',
  archived: 'study.planStates.archived',
}

export const STUDY_MASTERY_STATUS_KEYS: EnumLabelKeys = {
  needs_review: 'study.masteryStatuses.needsReview',
  developing: 'study.masteryStatuses.developing',
  mastered: 'study.masteryStatuses.mastered',
}

export const STUDY_AUTHORITY_KEYS: EnumLabelKeys = {
  ask: 'study.authorities.ask',
  coach: 'study.authorities.coach',
  plan: 'study.authorities.plan',
  create: 'study.authorities.create',
}

export const SOURCE_KIND_KEYS: EnumLabelKeys = {
  link: 'sources.kinds.link',
  upload: 'sources.kinds.upload',
  text: 'sources.kinds.text',
  web_import: 'sources.kinds.webImport',
  deep_research_report: 'sources.kinds.deepResearchReport',
}

export const KNOWLEDGE_TARGET_STATE_KEYS: EnumLabelKeys = {
  available: 'knowledge.targetStates.available',
  stale: 'knowledge.targetStates.stale',
  unavailable: 'knowledge.targetStates.unavailable',
  missing: 'knowledge.targetStates.missing',
}

export const MODEL_READINESS_KEYS: EnumLabelKeys = {
  ready_verified: 'settings.modelReadiness.readyVerified',
  ready_unverified: 'settings.modelReadiness.readyUnverified',
  requires_runtime: 'settings.modelReadiness.requiresRuntime',
  runtime_unavailable: 'settings.modelReadiness.runtimeUnavailable',
  installed_unsupported: 'settings.modelReadiness.installedUnsupported',
  incomplete: 'settings.modelReadiness.incomplete',
  planned: 'settings.modelReadiness.planned',
  removed: 'settings.modelReadiness.removed',
}

export const MODEL_HEALTH_STATUS_KEYS: EnumLabelKeys = {
  healthy: 'models.status.healthy',
  unhealthy: 'models.status.unhealthy',
  not_configured: 'models.status.notConfigured',
  unknown: 'models.status.unknown',
}

export const MODEL_RESOURCE_TIER_KEYS: EnumLabelKeys = {
  light: 'settings.modelTiers.light',
  standard: 'settings.modelTiers.standard',
  heavyweight: 'settings.modelTiers.heavyweight',
}

export const MODEL_SELECTION_SOURCE_KEYS: EnumLabelKeys = {
  automatic: 'settings.modelSelectionSources.automatic',
  role_override: 'settings.modelSelectionSources.roleOverride',
  production_override: 'settings.modelSelectionSources.productionOverride',
}

export const MODEL_ROLE_KEYS: EnumLabelKeys = {
  research_chat: 'settings.modelRoles.researchChat',
  evidence_extraction: 'settings.modelRoles.evidenceExtraction',
  claim_verification: 'settings.modelRoles.claimVerification',
  editorial_writing: 'settings.modelRoles.editorialWriting',
  embedding_retrieval: 'settings.modelRoles.embeddingRetrieval',
  vision_analysis: 'settings.modelRoles.visionAnalysis',
  code_data_analysis: 'settings.modelRoles.codeDataAnalysis',
  podcast_outline: 'settings.modelRoles.podcastOutline',
  podcast_script: 'settings.modelRoles.podcastScript',
  speech_to_text: 'settings.modelRoles.speechToText',
  text_to_speech: 'settings.modelRoles.textToSpeech',
  chat: 'settings.modelRoles.chat',
  source_synthesis: 'settings.modelRoles.sourceSynthesis',
  coding_research: 'settings.modelRoles.codingResearch',
  study_fast: 'settings.modelRoles.studyFast',
  embedding: 'settings.modelRoles.embedding',
}

export const RUNTIME_STARTUP_STAGE_KEYS: EnumLabelKeys = {
  launcher_start: 'workspace.runtimeStatusPanel.stages.launcherStart',
  chat_model_cache_hit: 'workspace.runtimeStatusPanel.stages.chatModelCacheHit',
  chat_model_scan: 'workspace.runtimeStatusPanel.stages.chatModelScan',
  core_ready: 'workspace.runtimeStatusPanel.stages.coreReady',
}

/**
 * v0.7.46 — Shared constants for api-keys/page.tsx and its extracted
 * subcomponents (DiscoverModelsDialog, future extractions).
 *
 * Pulled out so the splits can reference these without each carrying
 * its own copy. None of these are user-configurable at runtime;
 * adding a new provider means editing this file + the auto_register
 * Python side.
 */
import React from 'react'
import { Code, MessageSquare, Mic, Volume2 } from 'lucide-react'

export type ModelType =
  | 'language'
  | 'embedding'
  | 'text_to_speech'
  | 'speech_to_text'

export const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google AI',
  groq: 'Groq',
  mistral: 'Mistral AI',
  deepseek: 'DeepSeek',
  xai: 'xAI (Grok)',
  openrouter: 'OpenRouter',
  voyage: 'Voyage AI',
  elevenlabs: 'ElevenLabs',
  ollama: 'Ollama',
  azure: 'Azure OpenAI',
  vertex: 'Google Vertex AI',
  openai_compatible: 'OpenAI Compatible',
  dashscope: 'DashScope (Qwen)',
  minimax: 'MiniMax',
}

/** All supported providers, in display order. */
export const ALL_PROVIDERS = [
  'openai', 'anthropic', 'google', 'groq', 'mistral', 'deepseek',
  'xai', 'openrouter', 'dashscope', 'minimax', 'voyage', 'elevenlabs', 'ollama',
  'azure', 'vertex', 'openai_compatible',
] as const

/** Per-provider modalities (default offered when registering a model). */
export const PROVIDER_MODALITIES: Record<string, ModelType[]> = {
  openai: ['language', 'embedding', 'text_to_speech', 'speech_to_text'],
  anthropic: ['language'],
  google: ['language', 'embedding', 'text_to_speech', 'speech_to_text'],
  groq: ['language', 'speech_to_text'],
  mistral: ['language', 'embedding'],
  deepseek: ['language'],
  xai: ['language'],
  openrouter: ['language', 'embedding'],
  voyage: ['embedding'],
  elevenlabs: ['text_to_speech', 'speech_to_text'],
  ollama: ['language', 'embedding'],
  azure: ['language', 'embedding', 'text_to_speech', 'speech_to_text'],
  vertex: ['language', 'embedding', 'text_to_speech'],
  openai_compatible: ['language', 'embedding', 'text_to_speech', 'speech_to_text'],
  dashscope: ['language'],
  minimax: ['language'],
}

/** Where to point users to get an API key for each provider. */
export const PROVIDER_DOCS: Record<string, string> = {
  openai: 'https://platform.openai.com/api-keys',
  anthropic: 'https://console.anthropic.com/settings/keys',
  google: 'https://aistudio.google.com/app/apikey',
  groq: 'https://console.groq.com/keys',
  mistral: 'https://console.mistral.ai/api-keys/',
  deepseek: 'https://platform.deepseek.com/api_keys',
  xai: 'https://console.x.ai/',
  openrouter: 'https://openrouter.ai/keys',
  voyage: 'https://dash.voyageai.com/api-keys',
  elevenlabs: 'https://elevenlabs.io/app/settings/api-keys',
  azure: 'https://portal.azure.com/#view/Microsoft_Azure_ProjectOxford/CognitiveServicesHub/~/OpenAI',
  vertex: 'https://cloud.google.com/vertex-ai/docs/start/cloud-environment',
  openai_compatible: 'https://github.com/Antman1526/Deeper-Notebook/blob/main/docs/5-CONFIGURATION/openai-compatible.md',
  dashscope: 'https://help.aliyun.com/zh/model-studio/getting-started/',
  minimax: 'https://platform.minimaxi.com/document/Guides',
}

export const TYPE_ICONS: Record<ModelType, React.ReactNode> = {
  language: <MessageSquare className="h-3 w-3" />,
  embedding: <Code className="h-3 w-3" />,
  text_to_speech: <Volume2 className="h-3 w-3" />,
  speech_to_text: <Mic className="h-3 w-3" />,
}

// v0.8.130 — model types are identities in a set of four, not statuses, so they take the
// categorical chart tokens (UI audit Phase 1). The chip is a chart-colour tint with
// foreground text; chart-3 is skipped because it reads as near-white on light themes.
export const TYPE_COLORS: Record<ModelType, string> = {
  language: 'bg-chart-1/15 text-foreground',
  embedding: 'bg-chart-2/15 text-foreground',
  text_to_speech: 'bg-chart-5/20 text-foreground',
  speech_to_text: 'bg-chart-4/20 text-foreground',
}

export const TYPE_COLOR_INACTIVE =
  'bg-muted text-muted-foreground opacity-50'

/** Locale keys for the model-type chips; render with `t(TYPE_LABEL_KEYS[type])`. */
export const TYPE_LABEL_KEYS: Record<ModelType, string> = {
  language: 'apiKeys.typeLabels.language',
  embedding: 'apiKeys.typeLabels.embedding',
  text_to_speech: 'apiKeys.typeLabels.textToSpeech',
  speech_to_text: 'apiKeys.typeLabels.speechToText',
}

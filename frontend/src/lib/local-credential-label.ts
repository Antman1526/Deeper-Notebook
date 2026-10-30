// v0.8.130 — the desktop launcher registers local credentials under fixed English
// names, and those names are stored in the database (several places match on them
// by substring), so they cannot change. This translates them for display only.

type Translate = (key: string, vars?: Record<string, unknown>) => string

// Stored credential name -> the part before " (local)". `null` means the prefix is
// a translated word rather than a proper noun.
const LOCAL_CREDENTIAL_PREFIXES: Readonly<Record<string, string | null>> = {
  'Memory (local)': null,
  'Whisper (local)': 'Whisper',
  'Piper (local)': 'Piper',
  'Ollama (local)': 'Ollama',
  'LM Studio (local)': 'LM Studio',
  'MLX (local)': 'MLX',
  'llama.cpp (local)': 'llama.cpp',
}

/**
 * Display label for a credential name. Only the seven auto-registered names are
 * translated (exact, case-sensitive match); any other name, including a
 * user-chosen one that ends in "(local)", is returned unchanged.
 */
export function localCredentialLabel(name: string, t: Translate): string {
  if (!Object.prototype.hasOwnProperty.call(LOCAL_CREDENTIAL_PREFIXES, name)) return name
  const prefix = LOCAL_CREDENTIAL_PREFIXES[name] ?? t('models.localCredential.memory')
  return t('models.localCredential.named', { name: prefix })
}

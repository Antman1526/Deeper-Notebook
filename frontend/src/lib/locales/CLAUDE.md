# Locales Module (i18n)

Internationalization system providing multi-language UI support using i18next with standard `t()` function calls.

## Architecture

```
lib/
├── i18n.ts              # i18next initialization and configuration
├── i18n-events.ts       # Language change event emitters
├── hooks/
│   └── use-translation.ts  # Thin wrapper around react-i18next with language change events
├── utils/
│   └── date-locale.ts   # date-fns locale mapping
└── locales/
    ├── index.ts         # Locale registry and type exports
    ├── en-US/index.ts   # English: the source of truth for keys
    └── <code>/index.ts  # 13 more: bn-IN, ca-ES, de-DE, es-ES, fr-FR, it-IT, ja-JP,
                         #          pl-PL, pt-BR, ru-RU, tr-TR, zh-CN, zh-TW
```

Related: `components/common/RichText.tsx` renders translated sentences that contain
inline markup; `components/providers/DocumentTitle.tsx` sets the browser tab title
from the navigation keys; `components/providers/I18nProvider.tsx` keeps
`<html lang>` in step with the UI language; `lib/enum-labels.ts` maps API enum values
to keys.

## Key Components

- **`i18n.ts`**: i18next initialization with language detection (localStorage → browser)
- **`i18n-events.ts`**: Event emitters for language change start/end (used by loading overlay)
- **`locales/index.ts`**: Central registry exporting all locales and `LanguageCode` type
- **`use-translation.ts`**: Thin wrapper around react-i18next returning `{ t, i18n, language, setLanguage }`

## Translation Structure

Each locale file exports one nested object. Later additions are appended at the end of
the file as `Object.assign(ensureSection(rootNode, 'a'), { ... })` blocks (the same
helper exists in every locale), so a key's location can differ between files — search by
key path, not by line.

```typescript
export const enUS = {
  common: {
    save: 'Save',
    cancel: 'Cancel',
    delete: 'Delete',
    // ...
  },
  notebooks: {
    title: 'Notebooks',
    createNew: 'Create Notebook',
    // ...
  },
  // ... other sections
}
```

**Sections**:
- `common`: Shared UI elements (buttons, labels, actions)
- `notebooks`, `sources`, `notes`: Feature-specific strings
- `chat`, `search`, `podcasts`: Module-specific strings
- `models`, `transformations`, `settings`: Configuration UI
- `advanced`: System administration strings
- `apiErrors`: Backend error message translations

## Usage Pattern

```typescript
import { useTranslation } from '@/lib/hooks/use-translation'

function MyComponent() {
  const { t, language, setLanguage } = useTranslation()

  // Standard t() function call
  return <h1>{t('notebooks.title')}</h1>

  // With interpolation ({{name}} in the locale value). Older keys use a single-brace
  // {time} that callers substitute with .replace(); keep whichever style a key has.
  return <button>{t('knowledge.closeTab', { title })}</button>

  // A sentence with an inline element: ONE key with tags, never lead/tail fragments.
  // en-US: "Tip: hit <key/> from anywhere to jump to a notebook."
  return <RichText text={t('workspace.workspaceHome.tip')} components={{ key: () => <Kbd>⌘K</Kbd> }} />

  // Change language
  await setLanguage('zh-CN')
}
```

### Functions that accept t as a parameter

Use `TFunction` from i18next:

```typescript
import type { TFunction } from 'i18next'

const getNavigation = (t: TFunction) => [
  { name: t('navigation.sources'), href: '/sources' },
]
```

## Conventions (v0.8.130 whole-app pass)

- **No hard-coded UI English.** Every user-visible string — text, aria-label, title,
  placeholder, toast, confirm text — comes from `t()`. Product names (Deeper Notebook,
  Evidence Studio, Course Pack…), model names and code values stay literal.
- **Key names**: `<area>.<componentCamel>.<name>` (e.g. `study.tutorDock.emptyTitle`).
  Reuse an existing key only when its en-US value is character-identical.
- **Every key appears as a string literal in source** (`t('a.b')` or `'a.b'` in a map),
  so `keys-exist.test.ts` can check it. Avoid template-built keys.
- **No i18next plural suffixes** (`_one`/`_other`): key parity forbids per-language plural
  sets. Mirror the code's own branch with two keys (`sourceCountOne` / `sourceCountOther`).
  Russian and Polish write the Other form count-neutral ("Источников: {{count}}").
- **Inline elements** use one key with tags rendered by `RichText` (see above). Self-closing
  tags (`<path/>`) are filled by the component; wrapping tags (`<link>…</link>`) wrap
  translated text. `markup.test.ts` requires every locale to keep the en-US tags.
- **API enum values** shown as text go through `enumLabel(t, KEYS, value)` from
  `lib/enum-labels.ts`; unknown values fall back to the raw text.
- **en-US is sentence case** (`sentence-case.test.ts`); add genuine proper nouns to its list.
- **Terminology**: each locale keeps one word per concept, matching its `navigation.*`
  labels (e.g. de "Notizbuch", "Tresor"; it "quaderno"; Study ≠ Studio everywhere).
  German uses formal "Sie".

## Important Patterns

- **Standard t() calls**: `t('section.key')` — standard react-i18next pattern
- **Language persistence**: Saved to localStorage, auto-detected on load
- **Fallback**: Falls back to `en-US` if key missing in current locale
- **Date localization**: Use `getDateLocale(language)` from `utils/date-locale.ts`
- **Language change events**: `setLanguage` emits start/end events for `LanguageLoadingOverlay`

## Key Dependencies

- `i18next`: Core internationalization framework
- `react-i18next`: React bindings for i18next
- `i18next-browser-languagedetector`: Auto-detect browser language
- `date-fns/locale`: Date formatting locales

## How to Add a New Language

1. Create locale folder: `locales/pt-BR/index.ts`
2. Copy structure from `en-US/index.ts` and translate all strings
3. Register in `locales/index.ts`:
   ```typescript
   import { ptBR } from './pt-BR'
   export const resources = {
     // ...existing
     'pt-BR': { translation: ptBR },
   }
   export const languages: Language[] = [
     // ...existing
     { code: 'pt-BR', label: 'Português' },
   ]
   ```
4. Add to `utils/date-locale.ts`:
   ```typescript
   import { ptBR } from 'date-fns/locale'
   const LOCALE_MAP = { ...existing, 'pt-BR': ptBR }
   ```

## Important Quirks & Gotchas

- **Language change events**: `emitLanguageChangeStart/End` used by `LanguageLoadingOverlay` for UX
- **No SSR**: `useSuspense: false` disables React Suspense for i18next (avoids hydration issues)
- **All keys required**: Missing keys in non-English locales fall back to English; keep locales in sync
- **ErrorBoundary**: Uses raw `enUS` locale object directly (class component, can't use hooks)
- **Route titles**: Next.js route metadata renders on the server in English, so tab titles are
  set on the client by `DocumentTitle`; don't add `metadata.title` to route layouts.

## Testing Patterns

```typescript
// Mock useTranslation in tests (see test/setup.ts)
vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({
    t: (key: string) => key,  // Identity function returns the key
    language: 'en-US',
    setLanguage: vi.fn(),
  }),
}))

// The global mock returns the key and does no interpolation. Where an assertion needs
// a count or name, add a file-local mock that resolves the real en-US strings
// (see components/deeper-notebook/ArtifactRail.test.tsx) instead of dropping it.
```

Locale tests in this folder: `index.test.ts` (key parity), `placeholders.test.ts`,
`markup.test.ts`, `keys-exist.test.ts` (every literal key exists in en-US),
`sentence-case.test.ts`, `ui-audit-copy.test.ts`. `e2e/i18n-locales.spec.ts` checks the
live app in German and Japanese.

# 05 — Frontend Architecture & Components

> Recreation reference for the **Open Notebook Plus** web UI.
> Stack: **Next.js 16** (App Router) + **React 19** + TypeScript + **Zustand** +
> **TanStack Query (React Query)** + Tailwind CSS + Shadcn/Radix UI + **i18next**
> (10 locales). Dev server on `:3000`, talks to the FastAPI backend on `:5055`.

---

## 1. Layered architecture

```
Pages (src/app)  →  Feature components (src/components)  →  Hooks (src/lib/hooks)
                                                               ↓
                Zustand stores (src/lib/stores)  →  API client (src/lib/api)  →  Backend
```

Source root: `frontend/src/`. Top-level files: `proxy.ts` (Next 16 edge proxy / wizard gate),
`lib/`, `app/`, `components/`, `test/`.

---

## 2. App Router structure (`src/app`)

Next.js 16 App Router with **route groups** that organize without affecting the URL.

```
app/
├── layout.tsx                      # root layout — provider stack
├── page.tsx                        # / entry
├── config/route.ts                 # GET /config — runtime config (API URL) as a Route Handler
├── (auth)/
│   └── login/page.tsx              # /login
└── (dashboard)/                    # protected app shell (layout.tsx wraps all)
    ├── layout.tsx
    ├── page.tsx                    # dashboard home
    ├── notebooks/
    │   ├── page.tsx                # /notebooks (list)
    │   ├── [id]/page.tsx           # /notebooks/{id} — 3-column workspace
    │   └── components/             # ChatColumn, SourcesColumn, NotesColumn, NotebookHeader,
    │                               #   NotebookList/Card, *Dialog (Export/Import/Delete/NoteEditor),
    │                               #   BulkVectorizeButton  (+ co-located *.test.tsx)
    ├── sources/{page.tsx, [id]/page.tsx}
    ├── search/page.tsx
    ├── studio/page.tsx
    ├── podcasts/page.tsx
    ├── transformations/{page.tsx, components/*}   # editor, playground, optimize dialog, default-prompt editor
    ├── advanced/{page.tsx, components/SystemInfo, RebuildEmbeddings}
    ├── setup-wizard/page.tsx        # first-run wizard (target of proxy.ts)
    └── settings/
        ├── page.tsx, components/{SettingsForm, ObservabilityCard}
        ├── api-keys/{page.tsx, constants.tsx, components/DiscoverModelsDialog}
        ├── mcp/{page.tsx, RecommendationsPanel}
        ├── local-models/{page.tsx, DownloadPanel}
        └── launcher-prefs/page.tsx
```

**Pattern**: each `page.tsx` is a route endpoint that calls hooks for data and renders
feature components. Tests are co-located (`*.test.tsx`, Vitest).

---

## 3. Provider stack (`app/layout.tsx`)

Outermost → innermost:

1. `ErrorBoundary` — class component catching React render errors (uses raw `enUS` since it can't use hooks).
2. `ThemeProvider` — `next-themes` light/dark.
3. `QueryProvider` — TanStack Query client.
4. `I18nProvider` — i18next init + language-loading overlay.
5. `ConnectionGuard` — checks backend connectivity on startup.
6. `Toaster` — `sonner` toasts (inside `ConnectionGuard`).

---

## 4. Component hierarchy (`src/components`)

```
components/
├── layout/        AppShell.tsx, AppSidebar.tsx       # used by every page
├── providers/     ThemeProvider, QueryProvider, ModalProvider, I18nProvider
├── auth/          LoginForm.tsx
├── common/        CommandPalette, ErrorBoundary, ContextToggle, ModelSelector
├── ui/            Radix primitives + CVA styling (Button, Dialog, Input, …) — stateless
├── chat/          chat message rendering, streaming view
├── source/, sources/   source cards, dialogs, status pills
├── notebooks/     notebook-scoped composites
├── search/        ask/search results
├── podcasts/      episode list, generation controls, outline review
├── settings/      settings sub-components
├── errors/        error fallbacks
└── onp/           desktop-wrapper / launcher-specific UI
```

**Composition rule**: Pages → feature components (own page-level loading/error state) →
`ui/` components (stateless, styled). State is lifted into hooks rather than prop-drilled.

---

## 5. API client (`src/lib/api/client.ts`)

Single Axios instance, **10-minute timeout** (slow local-LLM ops), JSON default headers.

```ts
export const apiClient = axios.create({
  timeout: 600000, // 600s = 10 min
  headers: { 'Content-Type': 'application/json' },
  withCredentials: false,
})
```

### 5.1 Request interceptor

```ts
apiClient.interceptors.request.use(async (config) => {
  if (!config.baseURL) {
    const apiUrl = await getApiUrl()          // runtime config discovery
    config.baseURL = `${apiUrl}/api`
  }
  if (typeof window !== 'undefined') {
    const authStorage = localStorage.getItem('auth-storage')
    if (authStorage) {
      const { state } = JSON.parse(authStorage)
      if (state?.token) config.headers.Authorization = `Bearer ${state.token}`
    }
  }
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']     // let browser set multipart boundary
  } else if (['post','put','patch'].includes(config.method?.toLowerCase() ?? '')) {
    config.headers['Content-Type'] = 'application/json'
  }
  return config
})
```

- **Base URL discovery**: resolved once via `getApiUrl()` from runtime config; baked as `${apiUrl}/api`.
- **Auth**: Bearer token read from the Zustand `auth-storage` localStorage key.
- **FormData**: Content-Type deleted so the browser sets the multipart boundary. Nested JSON fields must be `JSON.stringify`-ed before being appended.

### 5.2 Response interceptor

- **401** → clear `auth-storage`, redirect to `/login` (guarded against `/login` → `/login` loops).
- **5xx** → toast at the interceptor level, deduped per `(status, url)` within a 5s window (`_SERVER_ERROR_DEDUPE_MS`). Callers opt out with header `x-skip-error-toast: '1'`. Messages distinguish 503 (service unavailable), 502 (bad gateway / local model unreachable), other 5xx (points to `~/.open-notebook-plus/logs/api.log`).

### 5.3 Resource modules

`src/lib/api/` exports namespaced objects per resource: `notebooks.ts`, `sources.ts`,
`notes.ts`, `chat.ts`, `source-chat.ts`, `search.ts`, `podcasts.ts`, `models.ts`,
`settings.ts`, `credentials.ts`, `transformations.ts`, `insights.ts`, `embedding.ts`,
`exports.ts`, `filesystem.ts`, `studio.ts`, `health.ts`, `onp.ts`. Each returns
`response.data` typed against `@/lib/types`. `query-client.ts` configures TanStack Query
(plus a checkpoint-prune test).

---

## 6. TanStack Query hooks (`src/lib/hooks`)

| Category | Hooks |
|---|---|
| Notebooks/sources/notes | `use-notebooks`, `use-sources`, `use-notes`, `use-insights` |
| Chat | `useNotebookChat`, `useSourceChat`, `use-ask` (SSE) |
| Models/settings | `use-models`, `use-settings`, `use-credentials`, `use-transformations` |
| Studio/podcasts | `use-studio`, `use-podcasts` |
| Local/infra | `use-local-models`, `use-mcp-servers`, `use-launcher-prefs`, `use-deep-health`, `use-system-status`, `use-network-status`, `use-db-repair-status`, `use-version-check` |
| Utility | `use-auth`, `use-media-query`, `use-modal-manager`, `use-navigation`, `use-toast`, `use-translation`, `use-fs`, `use-export`, `use-create-dialogs` |

Patterns:
- Data hooks return `{ data, isLoading, error, refetch }` via `useQuery` with `QUERY_KEYS.entity(id)` cache keys.
- Mutations use `useMutation` with `onSuccess` cache invalidation (often broad, e.g. `['sources']`) + `sonner` toast feedback. Toast copy comes from i18n keys; errors resolved via `getApiErrorKey()` / `getApiErrorMessage()`.
- **Status polling**: source/episode hooks `refetchOnWindowFocus` and poll every **2s** while status ∈ `{new, queued, running}`.
- **Credential hooks** (`use-credentials.ts`) expose `CREDENTIAL_QUERY_KEYS` (`all`, `status`, `envStatus`, `byProvider`, `detail`). `useTestCredential` keeps results in local state (not cached).

---

## 7. Zustand stores (`src/lib/stores`)

| Store | Purpose |
|---|---|
| `auth-store.ts` | token + auth status, persisted to `auth-storage` |
| `navigation-store.ts` | active route / nav state |
| `notebook-columns-store.ts` | 3-column workspace layout state |
| `sidebar-store.ts` | sidebar open/collapsed |
| `theme-store.ts` | theme prefs |

`auth-store.ts` (`create()(persist(...))`) — selective persistence via `partialize`
(only `token` + `isAuthenticated`), hydration tracking (`hasHydrated` / `onRehydrateStorage`),
and a 30-second `checkAuth()` cache. Token is validated by an actual `GET /api/notebooks`
call (not JWT decode):

```ts
checkAuth: async () => {
  const { token, lastAuthCheck, isCheckingAuth, isAuthenticated } = get()
  if (isCheckingAuth) return isAuthenticated
  if (!token) return false
  const now = Date.now()
  if (isAuthenticated && lastAuthCheck && (now - lastAuthCheck) < 30000) return true
  set({ isCheckingAuth: true })
  const apiUrl = await getApiUrl()
  const response = await fetch(`${apiUrl}/api/notebooks`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  })
  // 200 → authenticated; else clear token
}
```

`checkAuthRequired()` hits `GET /api/auth/status`; if `auth_enabled === false` it sets
`isAuthenticated: true, token: 'not-required'`.

---

## 8. SSE / streaming patterns

The frontend consumes two streaming endpoints: `/api/chat/stream` & source-chat `/messages`
(NDJSON) and `/api/search/ask` (SSE `data:` lines). The canonical implementation is
`use-ask.ts`:

```ts
const controller = new AbortController()
abortRef.current = controller
let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
try {
  const response = await searchApi.askKnowledgeBase({...}, controller.signal)
  reader = response.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const BUFFER_MAX = 4 * 1024 * 1024            // 4 MiB safety cap
  while (true) {
    if (!mountedRef.current) break              // unmount → stop reading
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    if (buffer.length > BUFFER_MAX) throw new Error('ask stream buffer exceeded 4 MiB')
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''                  // keep partial line
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6).trim())
        // strategy | answer | final_answer_delta | final_answer | complete | error
      }
    }
  }
} finally {
  if (reader) { await reader.cancel(); reader.releaseLock() }  // cancel BEFORE release
  if (abortRef.current === controller) abortRef.current = null
}
```

Hard-won patterns (each tagged with a version in-code):
- **`AbortController` + `mountedRef`** — cancel the in-flight stream on unmount or on a second `sendAsk`, preventing reader leaks and setState-after-unmount warnings.
- **`reader.cancel()` BEFORE `releaseLock()`** — actually tears down the HTTP body so the backend's `is_disconnected()` fires and the ask graph (multiple LLM calls) stops generating output nobody will read.
- **4 MiB buffer cap** — guards against a stream that never emits a newline (mirrors the source-chat cap).
- **Incomplete-line buffering** — last partial line is retained between reads; malformed JSON (`SyntaxError`) is logged and skipped, not thrown.
- **Ask event types**: `strategy`, `answer`, `final_answer_delta` (per-token), `final_answer` (canonical terminal), `complete`, `error`.

Chat stream (NDJSON) events from `/api/chat/stream`: `{"type":"start"}`, token deltas,
`{"type":"error"}`.

---

## 9. i18n system (`src/lib/i18n.ts`, `src/lib/locales`)

```ts
i18n.use(LanguageDetector).use(initReactI18next).init({
  resources,
  fallbackLng: 'en-US',
  interpolation: { escapeValue: false },     // React already XSS-safe
  react: { useSuspense: false },             // avoids hydration issues
  detection: { order: ['localStorage', 'navigator'], caches: ['localStorage'] },
})
```

**10 locales** registered in `locales/index.ts`:

| Code | Label | | Code | Label |
|---|---|---|---|---|
| `en-US` | English | | `it-IT` | Italiano |
| `zh-CN` | 简体中文 | | `fr-FR` | Français |
| `zh-TW` | 繁體中文 | | `ru-RU` | Русский |
| `pt-BR` | Português | | `bn-IN` | বাংলা |
| `ja-JP` | 日本語 | | `es-ES` | Español |

- Each `locales/<code>/index.ts` exports a nested object (sections: `common`, `notebooks`, `sources`, `notes`, `chat`, `search`, `podcasts`, `models`, `transformations`, `settings`, `advanced`, `apiErrors`, …). `TranslationKeys = typeof enUS` enforces shape; a completeness test asserts all locales share `en-US`'s keys.
- `use-translation.ts` wraps `react-i18next`'s `useTranslation`, returning `{ t, i18n, language, setLanguage }`. `setLanguage` emits start/end events (`i18n-events.ts`) used by `LanguageLoadingOverlay`.
- Missing keys fall back to `en-US`. Date formatting uses `utils/date-locale.ts` (`date-fns` locale map).

Usage: `const { t } = useTranslation(); t('notebooks.title')`.

---

## 10. Key feature flows

### 10.1 Notebook chat
`notebooks/[id]/page.tsx` → `ChatColumn` → `useNotebookChat()`:
queries sessions (TanStack Query), `buildContext()` assembles selected sources+notes
(token/char counts via `/api/chat/context`), `sendMessage()` calls `chatApi` with an
optimistic local message (removed on error), TanStack Query updates the cache, and broad
invalidation refreshes related source/note queries.

### 10.2 File upload → source creation
`SourceDialog` → `useFileUpload`: file → FormData (JSON fields stringified) → `sourcesApi.create()`.
The client interceptor strips Content-Type for FormData. Success toasts + `invalidateQueries(['sources'])`
cascade-refresh notebooks/sources lists. `async_processing: true` returns a `command_id`;
`useSourceStatus` then polls until terminal.

### 10.3 Podcasts
`podcasts/page.tsx` + `use-podcasts` — generate via `/api/podcasts/generate`, poll the job,
review/edit outline (`PUT …/outline`, `POST …/approve-outline`), retry failed episodes
(`retryEpisode()` / `useRetryPodcastEpisode()`), cancel running jobs.

### 10.4 Transformations
`transformations/page.tsx` + `use-transformations` — CRUD, a playground (`POST /api/transformations/execute`),
and an SkillOpt optimize dialog (`POST /api/transformations/{id}/optimize`).

---

## 11. Error handling

- API failures propagate to callers; components show `sonner` toasts.
- `lib/utils/error-handler.ts:getApiErrorMessage()` tries an i18n `ERROR_MAP` first, then falls back to the backend's descriptive message (so the backend's `classify_error()` text is shown as-is).
- App-level `ErrorBoundary` catches render errors with a fallback UI.
- 5xx toasts are centralized in the Axios response interceptor (deduped).

---

## 12. Routing / wizard gate

`src/proxy.ts` (Next 16 — renamed from `middleware.ts`) is the **edge proxy**. It does
**not** enforce auth (that's the Axios 401 interceptor). It redirects first-launch users to
`/setup-wizard` when the `wizard_completed` cookie is absent. See doc 06 for details.

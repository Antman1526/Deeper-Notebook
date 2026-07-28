# 05 — Frontend Architecture & Components

Exhaustive recreation reference for the Open Notebook Plus frontend. Everything
here is transcribed from the real source tree at
`frontend/src/` on branch `desktop-app`. Paths are repo-relative to
`/Users/Antman/Desktop/OpenNotebook/open-notebook-Plus`.

---

## 1. Stack & exact versions

Pinned from `frontend/package.json`:

| Package | Version | Role |
|---|---|---|
| `next` | `^16.2.3` | App Router framework (React 19, Webpack via Next) |
| `react` / `react-dom` | `^19.2.3` | UI runtime |
| `typescript` | `^5` | Language |
| `@tanstack/react-query` | `^5.83.0` | Server-state cache/fetch |
| `@tanstack/react-virtual` | `^3.13.24` | Virtualized lists |
| `zustand` | `^5.0.6` | Client state (auth, theme, layout, nav) |
| `@radix-ui/*` | accordion 1.2.12 … tooltip 1.2.7 | Headless UI primitives |
| `class-variance-authority` | `^0.7.1` | CVA variant styling |
| `clsx` + `tailwind-merge` | `^2.1.1` / `^3.3.1` | `cn()` class merge |
| `tailwindcss` | `^4` (`@tailwindcss/postcss` `^4`) | Tailwind v4 (oklch tokens, `@theme inline`) |
| `tw-animate-css` | `^1.3.5` | Animation utilities |
| `i18next` | `^25.7.3` | i18n core |
| `react-i18next` | `^16.5.0` | React bindings |
| `i18next-browser-languagedetector` | `^8.2.0` | localStorage → navigator detection |
| `framer-motion` | `^12.42.0` | Motion (intro reveal, transitions) |
| `react-pdf` | `^10.4.1` | PDF source viewer |
| `@xyflow/react` | `^12.11.1` | React Flow — MindMap |
| `react-resizable-panels` | `^2.1.9` | Draggable 3-pane workspace |
| `react-markdown` + `remark-gfm` + `remark-math` + `rehype-katex` | 10.1.0 / 4.0.1 / 6.0.0 / 7.0.1 | Chat/insight markdown + math |
| `@uiw/react-md-editor` | `^4.0.8` | Note/prompt editor |
| `sonner` | `^2.0.6` | Toasts |
| `lucide-react` | `^0.525.0` | Icons |
| `cmdk` | `^1.1.1` | Command palette |
| `react-hook-form` + `@hookform/resolvers` + `zod` | 7.60.0 / 5.1.1 / 4.0.5 | Forms + validation |
| `axios` | `^1.15.0` | HTTP client |
| `date-fns` | `^4.1.0` | Dates (+ per-locale mapping) |
| `next-themes` | `^0.4.6` | (present; the app mostly uses its own theme-store) |
| `use-debounce` | `^10.0.6` | Debounced inputs |

Dev/test: `vitest` `^4.1.8`, `@testing-library/react` `^16.2.0`, `jsdom`,
`@vitejs/plugin-react`, `eslint` `^9` + `eslint-config-next` `^16.2.6`,
`@next/bundle-analyzer`.

---

## 2. App Router route groups & pages

`frontend/src/app/` — directory-based routing. Route **groups** in parens
(`(auth)`, `(dashboard)`) organize files without contributing to the URL.

```
app/
  layout.tsx                     # root layout (providers)
  page.tsx                       # "/" root (redirect entry)
  globals.css                    # Tailwind v4 + oklch design tokens
  favicon.ico
  proxy.ts is at src/proxy.ts    # (NOT under app/) — Next 16 proxy (wizard redirect)

  (auth)/
    login/page.tsx               # /login — password entry

  (dashboard)/
    layout.tsx                   # auth-guard + ModalProvider + CommandPalette
    page.tsx                     # /  dashboard landing
    notebooks/page.tsx           # /notebooks list
    notebooks/[id]/page.tsx      # /notebooks/:id — 3-pane workspace
    notebooks/components/*       # ChatColumn, SourcesColumn, NotesColumn, NotebookHeader,
                                 #   NotebookCard/Row/List, dialogs (Export/Import/NoteEditor/Delete),
                                 #   BulkVectorizeButton
    sources/page.tsx             # /sources
    sources/[id]/page.tsx        # /sources/:id
    search/page.tsx              # /search (Ask)
    podcasts/page.tsx            # /podcasts
    studio/page.tsx              # /studio (artifacts)
    transformations/page.tsx (+ components/)
    advanced/page.tsx (+ RebuildEmbeddings, SystemInfo)
    setup-wizard/page.tsx        # first-launch wizard (sets wizard_completed cookie)
    settings/page.tsx
    settings/api-keys/page.tsx (+ DiscoverModelsDialog, constants.tsx)
    settings/local-models/page.tsx (+ DownloadPanel)
    settings/mcp/page.tsx (+ RecommendationsPanel)
    settings/launcher-prefs/page.tsx
    settings/components/*         # SettingsForm, ObservabilityCard, UpdatesCard

  api/                           # Next server routes (Node runtime) — SSE proxying only
    _sse-proxy.ts                # shared SSE reverse-proxy helper
    search/ask/route.ts          # POST → proxies /api/search/ask upstream (SSE)
    sources/[sourceId]/chat/sessions/[sessionId]/messages/route.ts  # SSE
  config/route.ts                # GET /config — runtime API URL discovery
```

### Root layout — provider nesting

`frontend/src/app/layout.tsx` (verbatim body):

```tsx
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className={inter.className}>
        <ErrorBoundary>
          <ThemeProvider>
            <QueryProvider>
              <I18nProvider>
                <ConnectionGuard>
                  {children}
                  <IntroReveal />
                  <Toaster />
                </ConnectionGuard>
              </I18nProvider>
            </QueryProvider>
          </ThemeProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
```

Provider order (outer → inner): `ErrorBoundary` → `ThemeProvider` →
`QueryProvider` → `I18nProvider` → `ConnectionGuard` → children + `IntroReveal`
(once-per-user "Aurora Reveal" splash) + `Toaster` (sonner). The pre-hydration
`themeScript` is injected in `<head>` to prevent theme flash. Global CSS imports:
`globals.css`, `katex/dist/katex.min.css`, and
`@/components/deeper-notebook/tokens.css` (the downstream token overlay).

### Dashboard auth guard

`frontend/src/app/(dashboard)/layout.tsx` — client component. It reads
`useAuth()`; while `isLoading` it shows a spinner, and once resolved, if
`!isAuthenticated` it stashes the current path in
`sessionStorage['redirectAfterLogin']` and `router.push('/login')`. When
authenticated it wraps children in `ErrorBoundary` → `CreateDialogsProvider` →
(children + `ModalProvider` + `CommandPalette`). It also calls
`useVersionCheck()` once per session.

---

## 3. Composition pattern: Pages → Feature components → UI components

Three layers (documented in `frontend/src/CLAUDE.md`):

```
Pages (App Router)  →  Feature components (state, loading/error)  →  UI components (stateless, styled)
        │                        │
        └── call hooks ──────────┴── hooks own data-fetch + business logic (TanStack Query / Zustand)
```

- **Pages** are thin: read route params, call hooks, render feature components.
- **Feature components** live in `components/<feature>/` (`source/`,
  `notebooks/`, `sources/`, `podcasts/`, `search/`, `chat/`, `onp/`,
  `settings/`, `layout/`, `common/`). They handle page-level state.
- **UI components** in `components/ui/` are shadcn/ui wrappers over Radix
  primitives with CVA variants — stateless and reused everywhere.

The canonical composition, from the notebook workspace:
`notebooks/[id]/page.tsx` → `ChatColumn` → `ChatPanel` → (`ContextIndicator`,
`SessionManager`, `ModelSelector`, `McpToolPicker`, `CitationPill`,
`ChatMessageProviderBadge`/`PrivacyBadge`/`AgentStateBadge`, `RunTimeline`) →
`ui/*` primitives.

`components/ui/` inventory: accordion, alert, alert-dialog, badge, button,
card, checkbox, checkbox-list, collapsible, command, dialog, dropdown-menu,
form-section, input, label, markdown-editor, popover, progress, radio-group,
resizable, scroll-area, select, separator, skeleton, sonner, tabs, textarea,
tooltip, virtualized-list, wizard-container.

---

## 4. Resizable 3-pane workspace

`frontend/src/app/(dashboard)/notebooks/[id]/page.tsx` is the most important
screen. It renders (desktop) a `ResizablePanelGroup` (react-resizable-panels@2)
of Sources / Notes / Chat, and (mobile) a `Tabs` switcher of the same three
columns to avoid double-mounting `ChatColumn`.

Desktop workspace (verbatim):

```tsx
<div className="hidden lg:flex h-full min-h-0 flex-1">
  <ResizablePanelGroup direction="horizontal" autoSaveId="onp-notebook-workspace" className="h-full">
    <ResizablePanel ref={sourcesPanelRef} collapsible collapsedSize={4} minSize={12} defaultSize={28}
      onCollapse={() => setSources(true)} onExpand={() => setSources(false)} className="min-w-0">
      <div className="h-full pr-3">
        <SourcesColumn sources={sources} isLoading={sourcesLoading} notebookId={notebookId}
          notebookName={notebook?.name} onRefresh={refetchSources}
          contextSelections={contextSelections.sources}
          onContextModeChange={(sourceId, mode) => handleContextModeChange(sourceId, mode, 'source')}
          onBulkContextModeChange={handleBulkSourceContext}
          hasNextPage={hasNextPage} isFetchingNextPage={isFetchingNextPage} fetchNextPage={fetchNextPage} />
      </div>
    </ResizablePanel>
    <ResizableHandle withHandle />
    <ResizablePanel ref={notesPanelRef} collapsible collapsedSize={4} minSize={12} defaultSize={28}
      onCollapse={() => setNotes(true)} onExpand={() => setNotes(false)} className="min-w-0"> … </ResizablePanel>
    <ResizableHandle withHandle />
    <ResizablePanel defaultSize={44} minSize={25} className="min-w-0"> … <ChatColumn/> … </ResizablePanel>
  </ResizablePanelGroup>
</div>
```

Key behaviors:

- **`autoSaveId="onp-notebook-workspace"`** persists panel widths to
  localStorage automatically.
- **Two-way collapse sync.** `useNotebookColumnsStore()` (Zustand) holds
  `sourcesCollapsed`/`notesCollapsed`. Imperative `ImperativePanelHandle` refs
  drive the panels from the store, while `onCollapse`/`onExpand` drive the store
  from the panel — guarded by `p.isCollapsed()` so they never loop:

  ```tsx
  useEffect(() => {
    const p = sourcesPanelRef.current
    if (!p) return
    if (sourcesCollapsed && !p.isCollapsed()) p.collapse()
    else if (!sourcesCollapsed && p.isCollapsed()) p.expand()
  }, [sourcesCollapsed])
  ```

- **Context selections** (`contextSelections: { sources: {}, notes: {} }`) are
  the single source of truth for what goes into chat context. Each source has a
  mode of `off | insights | full`; each note `off | full`. Effects
  `computeSourceSelections`/`computeNoteSelections` (from
  `lib/utils/source-context.ts`) initialize AND prune keys as the source/note
  lists change; the whole selection map is reset when `notebookId` changes.
- **`ArtifactRail`** (from `components/deeper-notebook`) sits above the panels; a
  `NotebookHeader` sits above that with a `border-b` divider. When a completed
  structured slide deck is selected, the rail queries completed podcast episodes,
  opens a native dialog to choose one with timestamped captions, and calls
  `useComposeVideoOverview()`. The returned local `/api/video-overviews/...`
  URLs are resolved through the existing API-base helper and rendered with a
  semantic `<video controls>` plus `<track kind="captions">`; the browser never
  receives a host filesystem path.

---

## 5. State management

### 5.1 Zustand stores (`lib/stores/`)

| Store | Persist key | Purpose |
|---|---|---|
| `auth-store.ts` | `auth-storage` | token, isAuthenticated, 30s auth-check cache (see doc 06) |
| `theme-store.ts` | `theme-storage` | `light`/`dark`/`system` (see §8) |
| `notebook-columns-store.ts` | — | `sourcesCollapsed`/`notesCollapsed` for the workspace |
| `notebook-view-store.ts` | — | notebook list/grid view mode |
| `navigation-store.ts` | — | active nav state |
| `sidebar-store.ts` | — | sidebar expanded/collapsed |

`persist` uses `partialize` to only save non-ephemeral fields (e.g. auth-store
persists just `{ token, isAuthenticated }`), and `onRehydrateStorage` to flip a
`hasHydrated` flag so SSR renders don't mismatch localStorage.

### 5.2 TanStack Query — client config & cache keys

`frontend/src/lib/api/query-client.ts`. Default options:

```ts
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60 * 1000, gcTime: 10 * 60 * 1000, retry: 2, refetchOnWindowFocus: false },
    mutations: { retry: shouldRetryMutation },
  },
})
```

`shouldRetryMutation` never retries 4xx (returns false for `status >= 400 && < 500`),
otherwise retries once. `QUERY_KEYS` is the hierarchical key registry:

```ts
export const QUERY_KEYS = {
  notebooks: ['notebooks'],
  notebook: (id) => ['notebooks', id],
  notes: (notebookId?) => ['notes', notebookId],
  note: (id) => ['notes', id],
  sources: (notebookId?) => notebookId ? ['sources','list',notebookId] : ['sources','list'],
  sourcesInfinite: (notebookId) => ['sources','infinite',notebookId],
  source: (id) => ['sources','detail',id],
  sourceStatus: (id) => ['sources','status',id],
  settings: ['settings'],
  observabilitySettings: ['settings','observability'],
  sourceChatSessions: (sourceId) => ['source-chat', sourceId, 'sessions'],
  sourceChatSession: (sourceId, sessionId) => ['source-chat', sourceId, 'sessions', sessionId],
  notebookChatSessions: (notebookId) => ['notebook-chat', notebookId, 'sessions'],
  notebookChatSession: (sessionId) => ['notebook-chat', 'sessions', sessionId],
  studioArtifacts: (notebookId) => ['studio', notebookId, 'artifacts'],
  studioArtifactRevisions: (artifactId) => ['studio','artifacts',artifactId,'revisions'],
  studioWorkflowRuns: (artifactId) => ['studio','artifacts',artifactId,'workflow-runs'],
  podcastEpisodes: ['podcasts','episodes'],
  podcastEpisode: (episodeId) => ['podcasts','episodes',episodeId],
  episodeProfiles: ['podcasts','episode-profiles'],
  speakerProfiles: ['podcasts','speaker-profiles'],
  languages: ['languages'],
}
```

**Source list-query predicate** (`lib/hooks/use-sources.ts`) — used to
invalidate *only* list/infinite queries without touching per-source
status polls:

```ts
export const _isSourcesListQuery = (queryKey) => {
  if (queryKey[0] !== 'sources') return false
  return queryKey[1] === 'list' || queryKey[1] === 'infinite'
}
```

**Ephemeral per-message cache pruning.** Chat hooks stash per-message badge
payloads under `['mcp','tool-calls',<id>]` and
`['chat','selected-provider',<id>]`. These accumulate over a session, so
`pruneMessageScopedQueries()` prefix-removes both families on chat-view unmount
(and on session switch).

### 5.3 Invalidation strategy (mutations)

Mutations invalidate broadly then narrowly. Example `useCreateSource`
(`lib/hooks/use-sources.ts`) invalidates each affected notebook's
`sources(nbId)` + `sourcesInfinite(nbId)` with `refetchType: 'active'`, the
generic `sources()` list, AND `QUERY_KEYS.notebooks` (so the sidebar's
`source_count` refreshes). `useUpdateSource`/`useDeleteSource` invalidate via the
`_isSourcesListQuery` predicate + the specific `source(id)`.

---

## 6. Data-fetching hooks (`lib/hooks/`)

Return shape convention: `{ data, isLoading, error, refetch }` plus action
functions. All wrap TanStack Query with `QUERY_KEYS`.

### 6.1 Source hooks (`use-sources.ts`)

- `useSources(notebookId?)` — flat list; `staleTime 60s`,
  `refetchOnWindowFocus: false` (the list endpoint fans out per-row subqueries,
  so on-focus refetch was too heavy).
- `useNotebookSources(notebookId)` — `useInfiniteQuery`, page size 30,
  offset-based (`getNextPageParam: lastPage => lastPage.nextOffset`), sorted
  `updated desc`. Flattens pages via `useMemo`; `refetch()` invalidates the
  infinite key.
- `useSource(id)` — detail; `staleTime 30s`, `refetchOnWindowFocus: true`.
- `useCreateSource`, `useUpdateSource`, `useDeleteSource`, `useFileUpload`,
  `useRetrySource`, `useAddSourcesToNotebook`, `useRemoveSourceFromNotebook` —
  mutations with sonner toasts (via `useToast`) + cache invalidation.
- `useSourceStatus(sourceId, enabled)` — **status polling**. `refetchInterval`
  returns `2000` while status is `running|queued|new`, but caps at `450` ticks
  (~15 min) then falls back to `30000`; returns `false` (stop) once
  `completed|failed`. `staleTime: 0`; retry stops on 404:

  ```ts
  refetchInterval: (query) => {
    const data = query.state.data as SourceStatusResponse | undefined
    if (data?.status === 'running' || data?.status === 'queued' || data?.status === 'new') {
      const ticks = query.state.dataUpdateCount ?? 0
      if (ticks > 450) return 30000
      return 2000
    }
    return false
  }
  ```

### 6.2 `useNotebookChat` (`lib/hooks/useNotebookChat.ts`) — flagship complex hook

Signature: `useNotebookChat({ notebookId, sources, notes, contextSelections })`.
Returns `{ sessions, currentSession, currentSessionId, messages, isSending,
loadingSessions, tokenCount, charCount, pendingModelOverride,
disabledMcpServers, toggleDisabledMcpServer, createSession, updateSession,
deleteSession, switchSession, sendMessage, cancelStreaming, setModelOverride,
refetchSessions }`.

Responsibilities:

1. **Session queries.** `useQuery(notebookChatSessions(notebookId))` lists
   sessions; `useQuery(notebookChatSession(currentSessionId))` fetches the
   active session + messages. Auto-selects the most recent session; on delete of
   the current session, jumps to the next session read from the *cache* (not the
   render closure) to survive rapid double-deletes.
2. **`buildContext()`** — translates `contextSelections` into a
   `context_config` map (`insights | 'full content' | 'not in'` per source;
   `'full content' | 'not in'` per note) and POSTs `/chat/build-context`,
   returning `{ context, token_count, char_count }`. Its `useCallback` deps are
   **stable string fingerprints** (`sourcesKey`, `notesKey`, `selectionsKey`),
   not array references — TanStack returns fresh arrays each refetch, which would
   otherwise re-POST on every poll.
3. **Streaming send.** `sendMessage(message, modelOverride?, bypassPrivacyGate?)`:
   - Auto-creates a session if none (title = first 30 chars), applying any
     `pendingModelOverride`.
   - Appends an optimistic human message keyed by a UUID `temp-${uuid}`, then a
     placeholder AI message `streaming-${uuid}`.
   - Binds a per-send `AbortController` (aborting any prior in-flight send).
   - Iterates `chatApi.streamMessage({...}, controller.signal)` — a
     `ChatStreamEvent` async generator. `token` events are **rAF-batched** into a
     `tokenBuffer` (≤1 setState per paint frame) rather than one setState/token.
     `mcp_tool_calls` stashes MCP payloads; `done` replaces the streamed buffer
     with the server's canonical message list and stashes badge data under
     `['mcp','tool-calls',id]` and `['chat','selected-provider',id]` (provider,
     model, `privacy_gated`, `privacy_categories`, `agent_state`,
     `offline_fallback`); `error` aborts.
   - Guards: `mountedRef` (no setState after unmount), `inFlightSendsRef`
     counter (blocks the `currentSession`→`setMessages` effect from clobbering
     optimistic state during rapid sends), and cleanup that filters *only this
     send's* IDs on error/abort.
4. **Per-conversation MCP disable picks** — `disabledMcpServers` state, hydrated
   from `currentSession.disabled_mcp_servers`, toggled via
   `toggleDisabledMcpServer` which PATCHes the session (best-effort) through a
   ref (`updateSessionMutationRef`) to dodge the JS temporal-dead-zone.
5. **Context-count effect** — recomputes `tokenCount`/`charCount` via
   `buildContext()`, protected by a monotonic `contextRequestSeq` counter so
   out-of-order responses from rapid toggling don't leave stale counts.
6. **`cancelStreaming()`** — public abort control for the UI (stop a runaway
   local-LLM generation); unmount also aborts + prunes ephemeral caches.

`ChatStreamEvent` (from `lib/api/chat.ts`) is the NDJSON wire union:

```ts
export type ChatStreamEvent =
  | { type: 'start'; session_id: string }
  | { type: 'token'; content: string }
  | { type: 'mcp_tool_calls'; calls: McpToolCall[] }
  | { type: 'done'; messages: NotebookChatMessage[]; selected_provider: string | null;
      selected_model_id: string | null; privacy_gated?: boolean | null;
      privacy_categories?: string[] | null; agent_state?: string | null;
      offline_fallback?: { offline_fallback: boolean; from_model_id?: string | null;
        to_model_id?: string | null; to_model_name?: string | null; reason?: string } | null }
  | { type: 'error'; detail: string }
```

### 6.3 `useAsk` (`lib/hooks/use-ask.ts`) — SSE streaming for the Ask workflow

Manual `ReadableStream` reader over `POST /api/search/ask`. State:
`{ isStreaming, strategy, answers, finalAnswer, error }`. `sendAsk(question,
{ strategy, answer, finalAnswer })`:

- Validates inputs, aborts any prior stream, resets state.
- Reads the body reader, decodes UTF-8 with a rolling `buffer`, splits on `\n`,
  keeps the trailing partial line. Each `data: {json}` line is parsed into an
  `AskStreamEvent`:
  - `strategy` → `{ reasoning, searches[] }`
  - `answer` → appended to `answers[]`
  - `final_answer_delta` → accumulated into `finalAccum`, **rAF-flushed**
  - `final_answer` → canonical replacement (cancels pending delta flush)
  - `complete` → stops streaming
  - `error` → throws
- **Buffer cap** `BUFFER_MAX = 4 MiB` — throws if a stream never emits a newline
  (transport corruption / server bug), preventing unbounded memory growth.
- **`finally` cleanup** — `await reader.cancel()` *before* `releaseLock()` so the
  HTTP body is actually torn down and the backend's `is_disconnected()` fires;
  clears the controller ref if still ours. `AbortError` is swallowed silently.

### 6.4 Other hooks

`use-notebooks`, `use-notes`, `use-search`, `use-podcasts`, `use-studio`,
`use-insights`, `use-models`, `use-settings`, `use-transformations`,
`use-credentials` (see api/CLAUDE.md), `use-export`, `use-fs`,
`use-local-models`, `use-mcp-servers`, `use-updates`, `use-version-check`,
`use-db-repair-status`, `use-deep-health`, `use-system-status`,
`use-network-status`, `use-launcher-prefs`, `use-sample-notebook`,
`use-notebook-graph` (MindMap data), plus utility hooks `use-media-query`
(`useIsDesktop`), `use-toast`, `use-navigation`, `use-auth`, `use-modal-manager`,
`use-translation`, `use-create-dialogs`.

---

## 7. Key feature components

### 7.1 `ChatColumn` → `ChatPanel`

`app/(dashboard)/notebooks/components/ChatColumn.tsx` fetches notes, wires
`useNotebookChat`, computes a `contextStats` memo (counts of
insights/full sources, notes, `totalSources`, `contextSourceTitles`, token/char
counts), fetches **corpus-grounded starter questions**
(`notebooksApi.suggestedQuestions(notebookId, 4)`, best-effort, only when there
are sources and no messages), and renders `ChatPanel`:

```tsx
<ChatPanel
  title={t('chat.chatWithNotebook')}
  contextType="notebook"
  messages={chat.messages}
  isStreaming={chat.isSending}
  onSendMessage={(message, modelOverride) => chat.sendMessage(message, modelOverride)}
  suggestedQuestions={showSuggestions ? suggestedQuestions : undefined}
  onSuggestedQuestionClick={(question) => chat.sendMessage(question)}
  onCancelStreaming={chat.cancelStreaming}
  … />
```

`components/source/ChatPanel.tsx` is the shared chat renderer for **both**
notebook chat and source chat (`contextType`). It renders markdown via
`react-markdown` + `remark-gfm` + `remark-math` + `rehype-katex`, splits
citations (`lib/utils/citations.ts`), renders `CitationPill`,
`ChatMessageProviderBadge` / `ChatMessagePrivacyBadge` /
`ChatMessageAgentStateBadge` (which read the per-message TanStack cache stashed
by the chat hook), `RunTimeline`, `SessionManager`, `ModelSelector`,
`McpToolPicker`, `MessageActions`/`MessageCopyEditActions`, and a
`ContextIndicator`. Exports a pure testable `isNearBottom(el, threshold=120)`
predicate used to keep auto-scroll pinned only when the user is near the bottom.

### 7.2 `SourcesColumn` / `SourceDetailContent`

`notebooks/components/SourcesColumn.tsx` renders the paginated source list with
per-card context-mode toggles (off/insights/full), infinite-scroll
(`hasNextPage`/`fetchNextPage`), and add/discover entry points.
`components/source/SourceDetailContent.tsx` is the full source viewer: title
inline-edit, Tabs (content / insights / etc.), markdown rendering, insights via
`insightsApi`, transformations via `transformationsApi`, embedding controls via
`embeddingApi`, PDF via a `next/dynamic` `PdfSourceViewer` (react-pdf, `ssr:false`).

### 7.3 `MindMap` (React Flow)

`components/notebooks/MindMap.tsx` — radial hub-and-spoke of notebook → sources
→ notes using `@xyflow/react` (`ReactFlow`, `Background`, `Controls`,
`MiniMap`). Data from `useNotebookGraph(notebookId, open)` → `GET
/api/notebooks/{id}/graph`. Node colors keyed by type
(`notebook: var(--primary)`, `source: #2563eb`, `note: #d97706`). Clicking a
source/note node deep-links via `onSelectSource`/`onSelectNote`. Loaded with
`next/dynamic` `ssr:false` (needs the DOM). `MindMapButton.tsx` is the trigger.

### 7.4 `DiscoverSourcesDialog`

`components/sources/DiscoverSourcesDialog.tsx` — user-driven web-search source
discovery. Type a topic → `POST /notebooks/{id}/discover-sources` → candidate
`DiscoverResult[]` → checkbox-select → add each as a link source through
`useCreateSource`. Privacy-forward: nothing leaves the machine until the user
searches AND a provider key is configured; the dialog names the active provider
and shows a setup hint when none is set.

### 7.5 `ContextIndicator`

`components/common/ContextIndicator.tsx` — the context summary bar under the chat
input. Shows "Using X of Y sources" (a `Popover` listing in-context source
titles when `totalSources` is provided), badges for insights/full source counts
and note count, and a right-aligned token/char summary formatted with K/M
suffixes (`formatNumber`). Falls back to a hint ("No sources or notes included…")
when nothing is in context and totals are unknown.

### 7.6 `AppShell` / `AppSidebar`

`components/layout/AppShell.tsx` is the shell used by every dashboard page:

```tsx
<div className="flex h-screen overflow-hidden">
  <AppSidebar />
  <main className="flex-1 flex flex-col min-h-0 overflow-hidden">
    <SetupBanner /><DbRepairBanner /><UpdateBanner /><NetworkStatusBadge />
    {children}
  </main>
</div>
```

`AppSidebar` renders nav + a version badge sourced from
`window.ONP_VERSION` (`(window as { ONP_VERSION?: string }).ONP_VERSION || '—'`).

---

## 8. Theming, aurora tokens & the desktop bridge

### 8.1 Two-layer token system

**Layer 1 — shadcn tokens (Tailwind v4, oklch).** `app/globals.css` declares
`@theme inline { --color-*: var(--*) }` mapping and `:root` / `.dark` blocks of
oklch design tokens plus custom `--success/--warning/--info`, a **motion scale**
(`--motion-fast/base/slow/spring`), and an **elevation scale**
(`--shadow-xs…xl`). Example:

```css
:root {
  --radius: 0.65rem;
  --background: oklch(1 0 0);
  --foreground: oklch(0.141 0.005 285.823);
  --primary: oklch(0.623 0.214 259.815);
  --destructive: oklch(0.577 0.245 27.325);
  --success: oklch(0.62 0.16 145);
  --warning: oklch(0.71 0.17 70);
  --info: oklch(0.62 0.18 230);
  --motion-base: 200ms cubic-bezier(0.4, 0, 0.2, 1);
  --shadow-lg: 0 10px 15px -3px rgba(15,23,42,0.08), 0 4px 6px -4px rgba(15,23,42,0.04);
}
```

**Layer 2 — Deeper Notebook downstream tokens.**
`components/deeper-notebook/tokens.css` layers `--dn-*` tokens *on top of* the
shadcn variables using `color-mix()` so they
auto-adapt to whichever of the 17 themes is active — no per-theme overrides.
This includes the **Aurora-glass system** (v0.8.70/72), which is theme-aware:
the aurora hues derive from the live theme's `--primary`/`--accent`:

```css
--dn-aurora-1: var(--primary, #2DD4BF);
--dn-aurora-2: var(--accent, #38BDF8);
--dn-aurora-3: color-mix(in oklab, var(--accent, #38BDF8) 55%, var(--primary, #2DD4BF));
--dn-glow-accent: 0 0 0 1px color-mix(in oklab, var(--primary) 26%, transparent),
                   0 10px 34px -8px color-mix(in oklab, var(--primary) 48%, transparent);
--dn-glass-bg: color-mix(in oklab, var(--card) 74%, transparent);
--dn-glass-blur: 14px;
```

`.dn-aurora-bg` renders layered drifting radial gradients
(`dn-aurora-drift` keyframes, GPU-composited transform/opacity/filter),
`.dn-glass` is the frosted-glass surface (backdrop-blur + saturate),
`.dn-aurora-text` is the gradient text used in the hero/intro.

### 8.2 Light/dark via `theme-store` + pre-hydration script

`lib/stores/theme-store.ts` (Zustand + persist `theme-storage`) holds
`light|dark|system`, and `setTheme` immediately toggles
`document.documentElement` classes + `data-theme`. `useTheme()` seeds
`effectiveTheme` as `'light'` (matching SSR) and only computes the real value in
a client `useEffect` to avoid hydration flicker; it also subscribes to
`prefers-color-scheme` when `theme === 'system'`. The flash-prevention
`themeScript` (`lib/theme-script.ts`) runs in `<head>` before hydration,
reading `theme-storage` from localStorage and applying the class/attribute.

### 8.3 The desktop `window.ONP` bridge

The native desktop wrapper (`desktop/window.py`) injects a `window.ONP` object.
The frontend feature-detects it and falls back gracefully in a plain browser.

**`window.ONP.setTheme(themeId)`** — used by
`components/deeper-notebook/ThemeSwitcher.tsx`. This component lists all 17
themes
(7 light incl. `system`, 10 dark) with per-theme `swatch`/`accent` dots. On
select:

```tsx
const handleSelect = (themeId: string) => {
  setActiveTheme(themeId)
  try { localStorage.setItem('onp-theme', themeId) } catch {}
  const w = window as OnpWindow & Window
  if (w.ONP?.setTheme) {
    w.ONP.setTheme(themeId)              // instant <html data-theme="…"> + POST /api/onp/theme (persist to config.toml)
  } else {
    onpFetch('/api/onp/theme', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: themeId }) }).catch(() => {})   // browser fallback
  }
}
```

`ONP_THEMES` is kept in lockstep with `desktop/window.py:_THEMES` and
`api/routers/onp.py`. On mount the switcher reads
`document.documentElement.dataset.theme` (already set by the injection JS), then
falls back to `localStorage['onp-theme']`, then `GET /api/onp/theme`.

**`window.ONP.relaunch()`** — used by `components/layout/DbRepairBanner.tsx` for
one-click "Repair & restart" (triggers the launcher's boot-time DB auto-repair).
Returns a boolean; a falsy result means no desktop bridge (dev/browser), so it
falls back to `window.location.reload()`:

```tsx
const handleRepairRestart = () => {
  const w = window as unknown as OnpRelaunchWindow & Window
  const relaunched = w.ONP?.relaunch?.()
  if (!relaunched) window.location.reload()
}
```

**`window.ONP_VERSION`** — a string the sidebar reads for its version badge.

**`onpFetch`** (`lib/api/onp.ts`) is a tiny auth-aware `fetch` wrapper for
`/api/onp/*` endpoints. It pulls the token from the same `auth-storage`
localStorage key axios uses, adds `Authorization: Bearer <token>`, and on 401
clears auth + bounces to `/login` (skipping the redirect if already on
`/login`) — mirroring the axios interceptor. The ONP components deliberately use
this instead of axios to keep their bespoke response handling.

---

## 9. i18n pattern (14 locales)

Locales: `en-US` (fallback), `zh-CN`, `zh-TW`, `pt-BR`, `ja-JP`, `it-IT`,
`fr-FR`, `ru-RU`, `bn-IN`, `ca-ES`, `es-ES`, `de-DE`, `pl-PL`, `tr-TR` —
registered in `lib/locales/index.ts` (`resources` map + `languages` array with
native labels). `TranslationKeys = typeof enUS` gives type safety; missing keys
in a non-English locale fall back to English.

`lib/i18n.ts` initializes i18next with `LanguageDetector`
(`order: ['localStorage','navigator']`, `caches: ['localStorage']`),
`fallbackLng: 'en-US'`, `interpolation.escapeValue: false`, and
`react.useSuspense: false` (avoids hydration issues).

`lib/hooks/use-translation.ts` is a thin wrapper returning
`{ t, i18n, language, setLanguage }`. `setLanguage` emits
`emitLanguageChangeStart/End` events (consumed by `LanguageLoadingOverlay`)
around `i18n.changeLanguage`.

**Usage convention: `t(key)` with an inline `defaultValue`.** Many newer
components pass a `defaultValue` so the string is legible even before the key is
added to every locale. Real example (`components/layout/DbRepairBanner.tsx`):

```tsx
<AlertTitle>{t('dbRepair.title', { defaultValue: 'Database needs repair' })}</AlertTitle>
<AlertDescription>
  <p>{t('dbRepair.description', { defaultValue:
      'Source processing is paused — … Restart to repair it automatically (a backup is taken first).' })}</p>
  <Button …>{t('dbRepair.repairRestart', { defaultValue: 'Repair & restart' })}</Button>
</AlertDescription>
```

Interpolation for older keys uses `.replace('{count}', …)` (see
`use-sources.ts` toasts). In tests, `useTranslation` is mocked so
`t` is the identity function (`t: (key) => key`).

---

## 10. API client & runtime base-URL discovery

`lib/api/client.ts` exports a single axios instance `apiClient`:

- **Timeout** defaults to `600000` ms (10 min) for slow local LLMs, overridable
  via `NEXT_PUBLIC_API_TIMEOUT_MS` (explicit `0` disables; empty/invalid falls
  back to default).
- **Request interceptor** lazily resolves `baseURL = ${await getApiUrl()}/api`,
  injects `Authorization: Bearer <token>` from `auth-storage`, and for FormData
  deletes `Content-Type` (browser sets the multipart boundary); otherwise sets
  JSON.
- **Response interceptor**: 401 → clear `auth-storage` + redirect to `/login`
  (unless already there); any 5xx → a deduped sonner toast (per `(status,url)`
  within 5 s), opt-out via `x-skip-error-toast: '1'`.

`lib/config.ts` resolves the API URL with a self-clearing promise cache
(so a startup race where the UI mounts before the FastAPI sidecar is ready
doesn't latch a permanent rejection). Priority: runtime `/config` endpoint →
`NEXT_PUBLIC_API_URL` → relative path (Next rewrites). `getConfig()` also
returns `version`, `latestVersion`, `hasUpdate`, `dbStatus`,
`sourceUploadMaxBytes`.

**Runtime config route** `app/config/route.ts` (`GET /config`, Node): returns
`{ apiUrl }` from `API_URL`/`NEXT_PUBLIC_API_URL`, else auto-detects from
request `host`/`x-forwarded-proto` headers (`${proto}://${hostname}:5055`), else
`http://localhost:5055`.

**SSE reverse-proxy** `app/api/_sse-proxy.ts` — server-side helper that forwards
`POST` bodies + the incoming `Authorization` header to
`${INTERNAL_API_URL || 'http://localhost:5055'}${upstreamPath}` with
`Accept: text/event-stream`, and streams the upstream body back with
`Content-Type: text/event-stream`, `Cache-Control: no-cache, no-transform`,
`X-Accel-Buffering: no`. Used by `app/api/search/ask/route.ts` and the
source-chat messages route (both `runtime = 'nodejs'`, `dynamic = 'force-dynamic'`).

---

## 11. Adding a feature (recipe)

1. `app/(dashboard)/feature/page.tsx` — call hooks, render feature components.
2. `components/feature/*` — compose UI + business logic.
3. `lib/hooks/useFeature.ts` — TanStack Query wrapper keyed via `QUERY_KEYS`.
4. `lib/api/feature.ts` — namespaced resource object over `apiClient`.
5. `lib/types/api.ts` — request/response shapes.
6. Reuse `components/ui/*`. Auth (401) and wizard redirects are handled by the
   axios interceptor and `src/proxy.ts` respectively — no per-component work.

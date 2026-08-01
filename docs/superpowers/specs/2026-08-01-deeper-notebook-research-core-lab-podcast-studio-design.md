# Deeper Notebook Research Core Lab and Podcast Intelligence Studio Design

**Date:** 2026-08-01

**Status:** Approved in conversational design; pending written-spec review

**Baseline:** local `main` at `d0101274`

**Delivery model:** one product direction delivered through three controlled
implementation phases

## Purpose

Turn Deeper Notebook's Knowledge workspace into its flagship Research Core Lab
and make source-grounded podcast production an optional first-class capability
for every notebook and note. Use Antman's existing local model library as a
first-class, automatically routed intelligence layer for research, evidence,
writing, vision, retrieval, podcast production, transcription, and voice.

The design must make Deeper Notebook competitive with Gemini Notebook while
preserving the product's distinct advantage: a durable, local-first knowledge
system that can continuously index and connect app-owned notes, Obsidian vaults,
and Logseq graphs without taking ownership of external files.

Google renamed NotebookLM to Gemini Notebook on 2026-07-16 and described a
research product with source-grounded chat, generated artifacts, code execution,
and wider Gemini ecosystem integration. Deeper Notebook will not imitate that
product's layout. It will compete by making research modes composable, keeping
knowledge alive across sessions, exposing exact provenance, and allowing the
user to move between notes, evidence, graphs, writing, chat, search, and audio
production inside one persistent workspace.

Official benchmark references:

- <https://blog.google/innovation-and-ai/products/gemini-notebook/notebooklm-gemini-notebook/>
- <https://support.google.com/gemininotebook/answer/16179559?hl=en>

## Product Position

Gemini Notebook helps a user understand a collection of sources. Deeper
Notebook helps a user build and operate a durable knowledge system.

That position is expressed through eight product advantages:

1. **Living knowledge:** mounted Obsidian and Logseq spaces remain continuously
   indexable rather than becoming disconnected upload snapshots.
2. **Equal research modes:** Read, Write, Ask, Search, Graph, and Podcast are
   first-class workspace modes.
3. **Evidence at every step:** answers, relationships, scripts, and audio claims
   can resolve to exact source blocks and revisions.
4. **Local-first control:** source content remains local, and provider choice
   stays explicit.
5. **Connected thinking:** notes, blocks, citations, tags, tasks, backlinks, and
   graph relationships share one navigation model.
6. **Reusable environments:** saved workspaces restore research context rather
   than only remembering a notebook name.
7. **Source authority:** app-owned content is editable while mounted external
   content remains visibly and technically read-only.
8. **Local intelligence ownership:** verified models in the user's Mac model
   library can perform specialized research roles without silently uploading
   source material or falling back to a cloud provider.

## Relationship to Existing Designs

This specification extends, rather than replaces, the approved designs for:

- the Deeper Notebook rebrand and Notebook Spark identity;
- read-only Second Brain integration;
- editor modes;
- command navigation;
- overlay productivity;
- the unified knowledge engine;
- navigation productivity; and
- the read-only Canvas viewer.

Existing identity, authority, workspace, command, search, backlink, graph,
provenance, bookmark, and persistence contracts remain authoritative unless
this specification explicitly adds a compatible extension.

## Existing Foundation

The baseline already provides:

- the Notebook Spark identity and Research Core teal-to-cyan palette;
- a recursive pane and tab workspace with durable split sizes;
- Reading, Source, Live Preview, Graph, and Canvas views;
- an autosaved Current Session and named workspace snapshots;
- one global command palette, a Knowledge quick switcher, and safe slash
  commands;
- unified knowledge documents, blocks, relations, revisions, identities,
  backlinks, graph reads, indexed search, and provenance;
- app-owned Overlay notes and external read-only Obsidian and Logseq mounts;
- bookmarks, workspaces, daily notes, random notes, and document metrics;
- podcast episode and speaker profiles;
- Brief, Deep Dive, Critique, and Debate podcast modes;
- source-driven podcast suggestions, length controls, and optional outline
  review;
- background podcast jobs, stage status, retry and cancellation;
- synchronized transcripts with citation IDs;
- a persistent global audio player;
- local MLX, llama.cpp, Ollama, and OpenAI-compatible provider support;
- local-model inventory, health, manifest reconciliation, and early role-routing
  APIs; and
- native MLX model discovery and registration through the desktop launcher.

The redesign must reveal and connect these capabilities before inventing
parallel replacements.

## Scope

### In scope

1. A Research Core Lab visual and interaction redesign of the Knowledge route.
2. Equal Read, Write, Ask, Search, Graph, and Podcast workspace modes.
3. A research header, collapsible Knowledge rail, adaptive pane canvas, and
   collapsible Intelligence rail.
4. Compact, consistent authority and availability indicators.
5. Optional podcast actions for every eligible notebook, note, source,
   selection, search result collection, bookmark, workspace, and graph cluster.
6. Quick Podcast and Podcast Studio launch paths.
7. A durable Research Set Manifest.
8. A source-grounded evidence blueprint and cited narrative storyboard.
9. Research-rigor controls and editorial-intelligence controls.
10. Versioned, resumable Research, Evidence, Storyboard, Script, Verification,
    Voice, and Episode artifacts.
11. A production-oriented Podcast library and completed Episode Lab.
12. Accessibility, responsive behavior, performance budgets, recovery states,
    and end-to-end proof.
13. Read-only discovery of the approved Mac model library at
    `/Users/Antman/Desktop/MacBook AI models`.
14. Automatic, inspectable role routing across verified compatible local
    language, vision, embedding, speech-to-text, and text-to-speech models.
15. Per-role and per-production model overrides, strict-local execution, memory
    governance, health proof, and explicit fallback behavior.

### Out of scope

- automatic podcast generation from newly created or changed content;
- requiring a podcast as part of any note or notebook workflow;
- writing podcast metadata into external Obsidian or Logseq files;
- enabling external-vault mutation commands;
- cloning Gemini Notebook's interface or Google ecosystem integrations;
- full visual redesign of non-Knowledge, non-Podcast routes;
- real-time multi-user collaboration;
- mobile-native clients;
- public podcast hosting, distribution, or automatic publishing;
- unattended publishing to feeds or social platforms;
- protected write-back to mounted vaults;
- automatically downloading, replacing, moving, or deleting model-library
  files during normal research;
- treating planned, removed, incomplete, or incompatible manifest entries as
  runnable models;
- adding a custom runtime for every Transformers or experimental repository in
  the library; and
- silent cloud fallback from a local-model task.

## Core Interaction Architecture

### Research header

The Knowledge route uses a compact header that communicates current context
without consuming document space. It contains:

- current knowledge space or named workspace;
- breadcrumb or active research trail;
- local model and provider readiness;
- watcher and index health;
- command search; and
- one Create action with context-aware destinations.

Status indicators disclose actionable state. They do not become a row of
decorative badges. A healthy watcher and index collapse into a quiet status;
warnings expand with an explanation and recovery action.

### Knowledge rail

The left side becomes a collapsible Knowledge rail. It preserves the current
Sources, Bookmarks, and Workspaces utilities and adds recent research without
creating a second navigation store.

The expanded rail can display:

- app-owned, Obsidian, and Logseq knowledge spaces;
- folders and files;
- bookmarks and bookmark folders;
- named workspaces and Current Session state; and
- recent or pinned research targets.

The collapsed rail retains accessible icon buttons and tooltips. Selecting a
rail mode never closes the active document or resets the canvas.

### Adaptive canvas

The existing recursive pane layout remains the durable canvas. It gains typed
tabs for these equal modes:

- `read`;
- `write`;
- `ask`;
- `search`;
- `graph`; and
- `podcast`.

Existing Source, Live Preview, Canvas, and other document-specific views remain
available inside their relevant document tabs. Equal mode status means that
Ask, Search, Graph, and Podcast can occupy full panes, tabs, or splits rather
than appearing only as temporary dialogs or fixed sidebars.

Any supported mode can open in the focused pane or in a new horizontal or
vertical split. Named workspaces and Current Session persist the supported mode
descriptor, active target, split sizes, and view-specific state.

Example arrangements include:

- source reading beside cited Ask results;
- synthesis writing beside an evidence inspector;
- graph exploration beside a filtered search;
- a research set beside its Podcast storyboard; and
- a completed episode transcript beside the cited source note.

### Mode launcher

A compact launcher exposes:

`Read · Write · Ask · Search · Graph · Podcast`

The launcher is a navigation instrument, not a permanent six-button banner.
It may appear in the research header, command palette, tab creation menu, and
appropriate empty states. Keyboard commands execute through the existing typed
command registry. Unavailable modes expose a stable reason and never partially
execute.

### Intelligence rail

The right side becomes a context-sensitive, collapsible Intelligence rail with
these views where supported:

- Outline;
- Backlinks;
- Evidence;
- Properties;
- Tasks; and
- Connections.

The rail follows the active pane. It does not maintain a separate active-note
identity. A document may expose Outline, Backlinks, Properties, Tasks, and
Connections. Ask and Podcast may expose Evidence and Connections. Graph may
expose filters, selected-node evidence, and connection details.

On narrower windows the rail becomes an accessible drawer. Hiding it never
discards its selected view or filters.

## Visual Language

### Research Core Lab

The selected direction is a futuristic research lab expressed as a precise
instrument rather than a gaming interface.

- Deep blue-green surfaces provide structure.
- A slightly lighter, quieter canvas supports long reading and writing.
- Teal identifies primary actions.
- Cyan edge light identifies active panes, focus, and selected graph
  relationships.
- Amber identifies uncertainty, stale evidence, and human review gates.
- Destructive color is reserved for actual failures or irreversible actions.
- Continuous decorative glow, particle fields, and looping animation are
  prohibited.

Existing semantic tokens remain the source of truth. The implementation may
add component-level Research Core variables but must not create a second
uncoordinated palette.

### Typography

Research content uses an editorial type treatment with readable line length,
generous leading, and clear heading rhythm. Controls use a precise sans-serif.
Source revisions, hashes, timing, counts, and generation stages use monospaced
or tabular numerals.

The implementation must resolve the current mismatch between the global Inter
font and Tailwind variables that reference Geist before adding a new font. Font
loading must remain local or use the existing Next.js font path; offline native
launch cannot depend on a remote font request.

### Motion and depth

Interaction motion uses the existing fast, base, and slow motion tokens.
Motion is limited to:

- active-pane emphasis;
- rail open and close transitions;
- tab and mode changes;
- graph selection and focus transitions; and
- podcast stage progression.

Motion uses transform and opacity where possible. Operating-system reduced
motion remains authoritative. Panel separation relies on tinted surfaces,
subtle inner edges, and consistent depth rather than generic card shadows.

### Authority presentation

Authority is always understandable but does not dominate tab width.

Compact states are:

- `Editable` for app-owned documents;
- `Obsidian · read-only` for mounted Obsidian content; and
- `Logseq · read-only` for mounted Logseq content.

The full explanation appears on focus, hover, source inspection, or attempted
use of an unavailable mutation. Authority must be conveyed by text or icon in
addition to color.

## Local Model Intelligence Router

### Approved library root

On Antman's Mac, the approved library root is:

`/Users/Antman/Desktop/MacBook AI models`

The desktop launcher exposes that selection through
`DEEPER_NOTEBOOK_MODEL_DIR`. The absolute path is a local device setting, not a
portable source-code constant. Other users and devices may choose another
folder without changing the product contract.

The library currently organizes assets under roots including `MLX`, `GGUF`,
`LMStudio`, `ollama`, `Transformers`, `STT`, and `TTS`. Discovery is read-only.
Normal research does not download, overwrite, rename, relocate, clean up, or
delete model files.

### Discovery and eligibility

The inventory classifies each discovered model as one of:

- `ready_verified`;
- `ready_unverified`;
- `requires_runtime`;
- `runtime_unavailable`;
- `installed_unsupported`;
- `incomplete`;
- `planned`; or
- `removed`.

`manifests/model_manifest.json` provides identity, role, revision, checksum,
and curation hints. It is not runtime proof. File completeness, supported
format, declared capabilities, memory fit, provider readiness, and a bounded
live health probe determine whether a route may execute.

The router must not select a manifest entry whose current state is planned,
removed, incomplete, incompatible, or unavailable. A model with an upstream
revision mismatch may remain installed and visible but is not automatically
promoted to a trusted route without an explicit local acceptance record.
`ready_unverified` models remain visible for diagnosis and explicit acceptance,
but automatic routing cannot use them until bounded runtime and acceptance
proof promotes them to `ready_verified`.

Native MLX discovery may serve complete MLX repositories through the existing
loopback `mlx_lm.server` path. GGUF models require a compatible llama.cpp-style
runtime. LM Studio and Ollama models require their corresponding local service
to be running and to report the expected model identity. Transformers and
experimental repositories remain visible but unsupported until a tested
runtime adapter exists.

Symlinked STT or TTS directories that resolve outside the selected root require
a separate, persisted local trust decision for the resolved target. The scanner
does not recursively follow arbitrary external symlinks.

### Automatic role routing

The selected approach is automatic role routing with visible overrides. The
router assigns independently versioned roles for:

- `research_chat` for Ask and grounded synthesis;
- `evidence_extraction` for claim and source analysis;
- `claim_verification` for the independent verification pass;
- `editorial_writing` for note and podcast narrative work;
- `embedding_retrieval` for semantic indexing and search;
- `vision_analysis` for supported document images and visual sources;
- `code_data_analysis` for code or structured-data work;
- `podcast_outline` for the evidence-backed storyboard;
- `podcast_script` for dialogue generation;
- `speech_to_text` for transcription; and
- `text_to_speech` for podcast voices.

Selection considers:

- verified compatibility and current health;
- task capability and modality;
- context capacity;
- benchmark and acceptance history;
- estimated unified-memory requirement;
- current memory pressure and loaded sidecars;
- expected latency; and
- user-pinned role or production-template overrides.

Manifest categories and role labels seed recommendations but never override
live readiness or resource safety. A coding model is not selected for
evidence synthesis merely because it is large, and a vision model is not
selected for text-only work when a smaller accepted model is sufficient.

The runtime records a stable model identity, local revision or fingerprint,
provider, route reason, and selection source (`automatic`, `role_override`, or
`production_override`) with every generated artifact. It does not store raw
credentials or expose the absolute model path in artifact API payloads. The
dedicated local Settings surface may display the user-selected library root.

### Overrides and execution policies

Before execution, the interface shows the selected model and the reason it was
chosen. The user may:

- accept the automatic route;
- pin a compatible model for a product role;
- override a model for one Ask, search, or podcast production; or
- save compatible model assignments in a Podcast template.

Three execution policies are available:

1. **Strict Local:** never contact a cloud model; fail closed when no accepted
   local route is ready.
2. **Local Preferred:** use an accepted local route first and ask before any
   cloud fallback.
3. **Custom:** use explicit per-role routes chosen by the user.

No policy silently sends notebook, note, evidence, prompt, transcript, or
podcast content to a cloud provider. Changing from local execution to cloud
execution is an explicit, contextual approval that identifies the affected
stage and content class.

### Mac resource governance

The default Mac policy loads at most one heavyweight MLX language model at a
time. Adjacent stages reuse a compatible loaded model when that does not weaken
the approved role contract. A required model change is queued and performed
through a controlled unload, memory-recovery, load, and health-check sequence.

Embedding, speech-to-text, or text-to-speech sidecars may coexist only when the
resource governor predicts that the combined workload remains inside the
configured unified-memory budget. The governor uses current memory pressure,
model size, active contexts, and sidecar reservations rather than model name
alone.

If a route cannot start:

- the task remains queued or fails with a stable reason;
- another accepted local candidate may be proposed;
- user-pinned assignments are never silently ignored;
- partial model processes are stopped and reported; and
- Strict Local never degrades to cloud execution.

### Product surfaces

The Research header shows quiet local readiness and expands to reveal the
active model, memory pressure, and queued work when attention is needed.

Settings → Local Models exposes:

- the approved library folder;
- rescan and health actions;
- format and runtime compatibility;
- verification and manifest-alignment state;
- role recommendations and overrides;
- local execution policy; and
- memory and concurrency limits.

Ask and Search show the active synthesis and embedding routes. Podcast Studio
shows a Model Plan for Evidence, Storyboard, Script, Verification, Voice, and
optional Transcription. The Model Plan is inspectable before generation and is
recorded with production history.

The model library is never presented as a flat list of folders alone. The UI
groups models by readiness, modality, supported role, and resource fit so an
installed but unusable model cannot be mistaken for a working route.

## Optional Podcast Contract

Every eligible notebook and note can become podcast input. No notebook or note
is required to become a podcast.

For this contract, every notebook and note exposed by Deeper Notebook is
eligible for the action. A temporarily unavailable, empty, failed-parse, or
unhydrated target keeps the action visible but disabled with the exact reason
generation cannot start. There is no hidden type, provider, or authority
allowlist that makes an otherwise readable notebook or note ineligible.

Podcast generation is always:

- secondary to normal note and notebook use;
- explicitly initiated by the user;
- cancelable before generation;
- incapable of modifying source content; and
- absent from automatic create, save, scan, watcher, or indexing flows.

The `Turn into podcast` action is available from appropriate menus and the
command palette for:

- an entire app-owned notebook;
- one or more app-owned notes;
- notebook sources;
- Obsidian notes or folders;
- Logseq pages, journals, or selected blocks;
- selected document blocks or text;
- search result collections;
- bookmarks or named workspaces;
- graph nodes or selected graph clusters; and
- the currently active supported tab.

The action offers two destinations:

1. **Quick Podcast:** use saved defaults and source-grounded recommendations,
   show a concise confirmation, then start production.
2. **Open in Podcast Studio:** open the complete Research Set for evidence,
   storyboard, and production review.

Dismissing either path leaves every source and workspace unchanged. No model,
voice, or audio work begins before explicit confirmation.

## Research Set Manifest

A podcast production begins with a durable Research Set Manifest. The manifest
stores stable knowledge references rather than an anonymous copied prompt.

It records:

- selected document and block IDs;
- saved-search or graph-selection descriptors where applicable;
- owning knowledge space and authority kind;
- relative source locator suitable for display;
- source revision and content fingerprint;
- inclusion mode and user-visible inclusion reason;
- central question, audience, purpose, and evidence policy; and
- unavailable, changed, duplicate, or intentionally excluded items.

The manifest never stores external absolute roots, credentials, environment
values, or write permissions. Generated context may be stored as an app-owned,
versioned production artifact when required for exact replay, but it never
becomes the authority for the external source.

### Whole-notebook and large-set behavior

Selecting a whole notebook includes every eligible note and source after a
reviewable manifest is built. Large research sets are partitioned into bounded
analysis batches, then synthesized into one evidence blueprint. Content is
never silently truncated.

Before generation, the selection review reports:

- included content;
- excluded content and reason;
- unavailable or unparsed content;
- changed content;
- duplicate or near-duplicate material;
- estimated analysis scope; and
- the effect of the selected evidence policy.

## Podcast Intelligence Studio

Podcast Studio is a full production surface that can open as a Knowledge tab
or from the Podcasts route. It replaces the oversized generation dialog as the
primary advanced workflow while retaining a concise Quick Podcast path.

### Layout

The production workspace uses:

- a left Research Set and evidence-coverage region;
- a central brief, evidence blueprint, and storyboard canvas;
- a right intellectual-controls and quality region; and
- a bottom production timeline or audio player.

On narrower windows, these regions become sequential accessible views rather
than compressed unreadable columns.

### Stage 1: Research Set

The user selects whole notebooks, notes, blocks, sources, searches, or graph
clusters. The studio shows authority, revision, inclusion state, context scope,
and missing material.

Source-driven recommendations may suggest a format, title, audience, or
profile. Every suggestion must include a short reason and remain editable.

### Stage 2: Editorial brief

The brief captures:

- central question;
- intended audience;
- Foundation, Practitioner, or Expert depth;
- Explain, Analyze, Challenge, Compare, or Teach purpose;
- Brief, Deep Dive, Critique, or Structured Debate format;
- target duration;
- required takeaway;
- desired unanswered-question summary;
- speaker profile and host roles; and
- evidence policy.

Host roles may include Lead Researcher, Explainer, Skeptic, and Domain
Specialist. Roles guide dialogue function; they do not claim real-world
credentials or identities that the selected voice does not possess.

### Stage 3: Evidence blueprint

Before dialogue generation, the engine identifies:

- major claims;
- supporting source blocks;
- counterarguments and conflicting evidence;
- uncertainty and interpretation;
- source diversity;
- unresolved questions;
- knowledge gaps; and
- proposed segment-to-evidence coverage.

Each claim receives one of these evidence states:

- `supported`;
- `contested`;
- `interpretive`;
- `unsupported`; or
- `unavailable`.

The state is inspectable and resolves to the supporting block and source
revision where applicable.

### Stage 4: Narrative storyboard

The storyboard is a production timeline. Each segment displays:

- title and narrative purpose;
- lead question;
- participating host roles;
- estimated duration;
- supporting claims and citations;
- counterpoint or uncertainty where relevant;
- learning outcome; and
- transition intent.

The user can reorder, rewrite, resize, add, or remove segments. Storyboard
approval is the default for Podcast Studio. A saved trusted template may enable
direct generation after the user explicitly chooses that behavior.

### Stage 5: Script and verification

Script generation consumes the approved storyboard and evidence blueprint.
Verification then checks:

- that factual claims map to approved evidence;
- that citations resolve to the recorded source revision;
- that contested claims retain the counterpoint;
- that interpretive language is labeled;
- that speaker roles remain consistent; and
- that length and audience constraints are respected.

Strict evidence mode prevents unlabeled unsupported factual claims from
reaching Voice. Interpretation mode permits analysis only when the script
identifies it as analysis, inference, hypothesis, or speculation.

### Stage 6: Voice and finalization

Voice generation operates on approved, verified segments. It produces audio,
timing, speaker lanes, chapter markers, and synchronized transcript metadata.
Finalization validates that audio and transcript segments correspond to the
approved script version.

### Episode Lab

A completed episode opens in Episode Lab with:

- waveform playback;
- chapters and speaker lanes;
- synchronized transcript;
- clickable citations;
- source coverage and evidence states;
- generation and approval history;
- downloadable app-owned artifacts where currently supported; and
- segment-level regeneration.

Selecting a citation moves from the audio claim to transcript text, evidence
block, original note, and recorded source revision. Regenerating one segment
creates a new segment version and leaves unaffected segments unchanged.

### Podcast library

The Podcasts route organizes work by production intent rather than presenting
only status-grouped cards:

- Continue Production;
- Ready to Review;
- Completed; and
- Needs Attention.

Episode and speaker templates remain available. Filters include format,
knowledge space, profile, evidence state, date, and production stage. The
global audio player continues across route changes.

## Versioning and Recovery

The durable production graph is:

`Research Set → Evidence → Storyboard → Script → Verification → Voice → Episode`

Each stage produces a versioned app-owned artifact with a stable production ID
and explicit parent version. Changing an upstream artifact marks dependent
artifacts stale; it does not delete them.

Recovery rules are:

- retries use stable idempotency keys and do not create duplicate episodes;
- failure resumes from the affected stage;
- Evidence or Verification failure returns to the relevant review surface;
- Voice failure preserves the approved script;
- segment regeneration affects only that segment and final assembly;
- cancellation preserves completed artifacts as a draft;
- missing source records remain visible rather than being silently removed;
- changed sources offer Refresh Evidence or Continue with Recorded Revision;
  and
- every episode exposes its manifest, versions, approvals, and failure history.

## Source Authority and Security

All external knowledge remains `external_read_only` throughout this design.

- Podcast selection reads through unified knowledge APIs.
- Frontend components never open canonical external paths directly.
- Podcast artifacts are written only to app-owned storage.
- The system never writes backlinks, status, metadata, transcript, or audio
  references into mounted vaults.
- Command registration classifies podcast creation as an app-owned mutation
  that reads external evidence; it is not an external write.
- External rename, move, delete, task toggle, property edit, or body edit
  commands remain unavailable.
- Source fingerprints are compared before refresh or replay.
- API responses disclose stable relative provenance rather than source roots.

## Error and Readiness States

The system checks readiness before expensive generation:

- research-set hydration;
- required model roles, accepted local revisions, and bounded live health;
- voice profile and voice model;
- local storage availability;
- evidence policy viability; and
- background worker availability.

Unavailable requirements disable generation with a stable explanation and a
direct setup or recovery action. One failed knowledge space does not discard
healthy selections from other spaces.

Loading uses structure-matched skeletons. Empty states explain the first useful
action. Errors remain inline with the failed stage; they do not rely on raw
provider messages or generic alerts.

## Accessibility and Responsive Behavior

The design must preserve or improve:

- semantic `header`, `nav`, `main`, `article`, `aside`, and `section` regions;
- keyboard access to every mode, pane, rail, stage, and review action;
- visible high-contrast focus;
- focus restoration after dialogs and drawers;
- screen-reader announcements for generation-stage changes;
- non-color authority and evidence labels;
- reduced-motion behavior;
- minimum target sizes for pointer and touch input;
- zoom to 200 percent without lost controls; and
- responsive conversion of side rails into drawers or sequential views.

The storyboard must support keyboard reorder controls in addition to drag and
drop. Waveform and graph views require equivalent textual navigation.

## Performance

The visual redesign must not make the native app dependent on continuous GPU
effects. No decorative animation runs indefinitely.

Implementation budgets include:

- lazy-loading Graph and Podcast Studio code when the mode first opens;
- virtualizing large source, search, and episode lists where existing limits
  are exceeded;
- debouncing evidence-scope recalculation;
- batching large Research Set analysis with visible progress;
- avoiding duplicate hydration across split panes;
- keeping collapsed rails unmounted or inert where safe;
- preserving responsive pane resize and document scrolling during background
  generation;
- loading only one heavyweight MLX language model by default;
- reusing a compatible loaded model across adjacent stages;
- reserving memory before starting embedding, transcription, or voice sidecars;
  and
- queuing model swaps rather than starting competing heavyweight runtimes.

## Delivery Phases

### Phase 1: Research Core Lab

- research header and collapsible rails;
- equal mode launcher and typed mode tabs;
- adaptive canvas integration;
- typography, surface, focus, and authority improvements;
- responsive and accessible behavior;
- preservation of current commands, workspaces, document modes, graph,
  backlinks, bookmarks, and persistence; and
- local-library selection, verified inventory, role-routing status, and the
  Research-header local readiness surface.

Phase 1 does not require the new podcast evidence pipeline.

### Phase 2: Podcast Studio experience

- optional `Turn into podcast` actions;
- Quick Podcast confirmation;
- Research Set selection and manifest preview;
- full Podcast Studio route or pane surface;
- visual storyboard and production timeline;
- production-oriented Podcast library;
- reuse of current profiles, modes, outline review, jobs, transcript, citation,
  player, cancellation, and retry behavior; and
- an inspectable Podcast Model Plan using accepted local role routes and
  explicit per-production overrides.

Phase 2 may adapt current backend contracts but must not pretend that the Phase
3 evidence engine exists before it does.

### Phase 3: Intellectual production engine

- durable Research Set Manifest;
- claim-level evidence blueprint;
- counterarguments, contradictions, uncertainty, and gaps;
- intellectual and editorial controls;
- cited storyboard and script verification;
- artifact version graph;
- source-change decisions;
- resumable stage and segment generation;
- Episode Lab evidence inspection;
- independent local routes for Evidence, Script, and Verification where the
  accepted library and Mac memory budget permit them; and
- artifact receipts recording model identity, revision, provider, and route
  reason without exposing canonical model paths.

Each phase requires its own implementation plan and verification record. The
application must remain usable at the end of every phase.

## Test Strategy

### Pure and component tests

- mode descriptors and availability reasons;
- authority and evidence-state presentation;
- optional podcast action visibility and absence of automatic execution;
- Research Set manifest normalization and deduplication;
- whole-notebook inclusion rules;
- large-set batching without silent truncation;
- storyboard editing and keyboard reorder;
- evidence-policy gating;
- source-change state transitions;
- stage version invalidation;
- idempotency keys and segment regeneration boundaries;
- accessible names, roles, focus, and reduced motion;
- model-role scoring and deterministic tie-breakers;
- role and production override precedence;
- planned, removed, incomplete, unverified, and unsupported model states;
- Strict Local and Local Preferred policy presentation; and
- model-plan receipts that redact canonical paths.

### API and integration tests

- writable and external read-only inputs in one Research Set;
- stable document, block, revision, and provenance references;
- missing, changed, duplicate, failed-parse, and unavailable sources;
- provider, model, voice, storage, and worker readiness;
- strict and interpretation evidence policies;
- retry and cancellation at every durable stage;
- exact preservation of approved upstream artifacts after downstream failure;
- no duplicate episode after retry;
- redaction of canonical roots and provider error details;
- discovery from `/Users/Antman/Desktop/MacBook AI models`, including the
  spaces in the path;
- packaged-app restart with the selected library preserved;
- compatibility-alias and separately approved external-symlink behavior;
- manifest reconciliation against current installed files;
- live runtime identity mismatch and health-probe failure;
- memory-budget rejection and queued model swaps;
- one-heavyweight-MLX default enforcement;
- zero network requests to cloud-model endpoints in Strict Local mode; and
- exact model-library fingerprint preservation after discovery and execution.

### Browser tests

- open every equal mode from the launcher and command palette;
- split modes and restore them from Current Session and a named workspace;
- navigate citation to exact evidence and back;
- start optional podcast production from a notebook, note, selected block,
  search result set, and graph cluster;
- dismiss podcast actions without side effects;
- review a whole-notebook manifest;
- edit and approve a storyboard;
- recover a failed Voice stage without regenerating Research or Script;
- use Episode Lab transcript, citation, and segment regeneration;
- inspect and override automatic local routes;
- reject an incompatible model without losing the current research task;
- view Podcast Model Plan and production model receipts;
- complete a Strict Local podcast run without cloud fallback;
- complete all primary flows by keyboard; and
- verify responsive drawers at supported viewport widths.

### Protected-source proof

For representative Obsidian and Logseq fixtures and the controlled Second Brain
mounts:

- record source hashes before tests;
- run selection, evidence, storyboard, script, retry, and playback flows;
- record hashes after tests;
- require exact equality; and
- require zero external write attempts in API and filesystem receipts.

## Acceptance Criteria

The program is complete only when:

1. Read, Write, Ask, Search, Graph, and Podcast are equal, restorable workspace
   modes.
2. The Research Core Lab is visually distinct, readable for long sessions, and
   free of continuous decorative motion.
3. Existing Knowledge and Podcast capabilities remain functional.
4. Every eligible notebook and note offers optional podcast generation.
5. No podcast work starts without explicit user initiation and confirmation.
6. Whole notebooks are processed without silent truncation.
7. Strict evidence mode prevents unlabeled unsupported factual claims from
   reaching audio.
8. Audio claims can resolve through transcript and evidence to the recorded
   source revision.
9. Failed work resumes without duplicate episodes or discarded approved
   artifacts.
10. Obsidian and Logseq source fingerprints remain unchanged.
11. Keyboard, screen-reader, contrast, reduced-motion, responsive, and zoom
    gates pass.
12. Phase-specific component, API, integration, browser, production-build, and
    native-runtime verification passes with recorded evidence.
13. The selected Mac model library is discovered without modifying its files,
    and only verified compatible live routes execute automatically.
14. Ask, evidence, verification, editorial, retrieval, vision, podcast, STT,
    and TTS roles expose automatic recommendations and explicit overrides.
15. Strict Local produces zero cloud-model requests and never silently falls
    back after a local failure.
16. The Mac resource governor prevents competing heavyweight MLX loads and
    preserves application responsiveness during queued model changes.

## Approved Defaults

- Scope begins with the Knowledge workspace rather than a whole-app redesign.
- The visual direction is Research Core Lab.
- Read, Write, Ask, Search, Graph, and Podcast have equal status.
- The workspace is adaptive and persists tabs and splits.
- Podcast generation is optional and always user-initiated.
- Research rigor and editorial intelligence are both required.
- Podcast Studio pauses for storyboard approval by default.
- Strict evidence is the default evidence policy.
- External Obsidian and Logseq content remains read-only.
- The current Mac library root is
  `/Users/Antman/Desktop/MacBook AI models` through a local configurable
  setting rather than a portable source constant.
- Local models use automatic role routing with visible per-role and
  per-production overrides.
- Strict Local is available and fails closed; cloud fallback is never silent.
- One heavyweight MLX language model is loaded at a time by default.
- The work ships in three independently verifiable phases.

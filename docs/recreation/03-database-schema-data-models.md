# 03 — Database Schema & Data Models

> Recreation reference for **Open Notebook Plus** (`desktop-app` branch).
> Persistence tier: **SurrealDB** (graph DB with native vector search + full-text
> BM25 search). All access goes through the async repository layer
> (`open_notebook/database/repository.py`) and Pydantic domain models
> (`open_notebook/domain/`, `open_notebook/ai/models.py`,
> `open_notebook/podcasts/models.py`). Schema is applied by numbered SurrealQL
> migrations run automatically on API startup.

This document is exhaustive enough to rebuild the schema and the domain layer
from scratch. Field lists are copied verbatim from the Pydantic models; table
definitions are copied from the `.surrealql` migrations.

---

## 1. Storage & connection model

- **Engine**: SurrealDB (`surrealdb>=1.0.4` async driver). Default endpoint
  `ws://localhost:8000` namespace/database configurable via env.
- **Connection resolution** (`repository.py`):
  - `get_database_url()` — `SURREAL_URL`, else built from `SURREAL_ADDRESS` +
    `SURREAL_PORT`.
  - `get_database_password()` — `SURREAL_PASSWORD`, falling back to legacy
    `SURREAL_PASS`.
  - Namespace/database selected after sign-in inside the `db_connection()` async
    context manager.
- **Pooling**: A DB pool lazy-initializes on the first `repo_query` call
  (v0.7.18). Pool size via `ONP_DB_POOL_SIZE` (default 4). Pool is drained on
  API shutdown.
- **Repository functions** (all async): `repo_query(query, vars)`,
  `repo_create(table, data)`, `repo_insert(table, data_list, ignore_duplicates)`,
  `repo_upsert(table, id, data, add_timestamp)`, `repo_update(table, id, data)`,
  `repo_delete(record_id)`, `repo_relate(source, relationship, target, data)`.
- **Helpers**: `ensure_record_id(value)` coerces `str | RecordID` → `RecordID`;
  `parse_record_ids(obj)` recursively stringifies `RecordID`s in a result tree.
- **Timestamps**: `repo_create` / `repo_update` auto-set `created` / `updated`.
  The domain `ObjectModel.save()` writes them as **aware-UTC ISO-8601 strings**
  (v0.7.187 — `datetime.now(timezone.utc).isoformat()`), not naive local time.

### 1.1 Two persistence base classes (`open_notebook/domain/base.py`)

**`ObjectModel`** — mutable records with SurrealDB auto-IDs.

```python
class ObjectModel(BaseModel):
    id: Optional[str] = None
    table_name: ClassVar[str] = ""
    nullable_fields: ClassVar[set[str]] = set()  # fields allowed to persist as None
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
```

Key behaviors:
- `get(id)` — **polymorphic** fetch; resolves the subclass from the ID's table
  prefix (`table:id`) by scanning `ObjectModel.__subclasses__()`. Fails if the
  subclass module isn't imported.
- `get_all(order_by, limit, offset)` — table scan; `order_by` is validated
  against `^[a-z_][a-z0-9_]*$` + `{asc,desc}` (SurrealQL-injection guard);
  `limit`/`offset` validated as positive/non-negative ints (rejects `bool`),
  raising `InvalidInputError` (→ HTTP 400) *before* the DB call.
- `save()` — validates, calls `_prepare_save_data()`, then `repo_create` (new)
  or `repo_update` (existing). `_prepare_save_data()` drops `None` values
  **unless** the key is in `nullable_fields`.
- `_coerce_id_to_str` validator (v0.8.66 D-6) — every model coerces a raw
  `RecordID` id to `str` uniformly.

**`RecordModel`** — **singletons** with a fixed `record_id` (config records).
`__new__` returns the cached instance per `record_id`; `update()` does an
`repo_upsert`; `get_instance()` loads from DB lazily; `clear_instance()` resets
for tests.

---

## 2. Record tables

Below, each table is given with its migration-defined SurrealQL schema and its
Pydantic domain model (verbatim field list). Unless noted, `created`/`updated`
are `datetime` auto-managed on every table.

### 2.1 `notebook` (SCHEMAFULL) — research project container

Migration `1.surrealql`:
```surql
DEFINE TABLE IF NOT EXISTS notebook SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name        ON TABLE notebook TYPE option<string>;
DEFINE FIELD IF NOT EXISTS description ON TABLE notebook TYPE option<string>;
DEFINE FIELD IF NOT EXISTS archived    ON TABLE notebook TYPE option<bool> DEFAULT False;
DEFINE FIELD IF NOT EXISTS created ON notebook DEFAULT time::now() VALUE $before OR time::now();
DEFINE FIELD IF NOT EXISTS updated ON notebook DEFAULT time::now() VALUE time::now();
```

Domain model (`open_notebook/domain/notebook.py`):
```python
class Notebook(ObjectModel):
    table_name: ClassVar[str] = "notebook"
    name: str
    description: str
    archived: Optional[bool] = False
    # name_must_not_be_empty validator → InvalidInputError on blank name
```
Navigation methods: `get_sources()`, `get_notes()`, `get_chat_sessions(limit,
offset)`, `get_graph()` (mind-map: notebook hub + source/note nodes),
`get_delete_preview()`, `delete(delete_exclusive_sources)`. See §5 for cascade.

### 2.2 `source` (SCHEMAFULL) — ingested content item

Migration `1.surrealql` (+ `25.surrealql` adds `provenance`, `source_type`;
`8.surrealql` adds `command`):
```surql
DEFINE TABLE IF NOT EXISTS source SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS asset     ON TABLE source FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS title     ON TABLE source TYPE option<string>;
DEFINE FIELD IF NOT EXISTS topics    ON TABLE source TYPE option<array<string>>;
DEFINE FIELD IF NOT EXISTS full_text ON TABLE source TYPE option<string>;
DEFINE FIELD IF NOT EXISTS created ON source DEFAULT time::now() VALUE $before OR time::now();
DEFINE FIELD IF NOT EXISTS updated ON source DEFAULT time::now() VALUE time::now();
-- migration 8:
DEFINE FIELD IF NOT EXISTS command    ON source TYPE option<record<command>>;
-- migration 25:
DEFINE FIELD IF NOT EXISTS provenance  ON TABLE source FLEXIBLE TYPE option<object> DEFAULT {};
DEFINE FIELD IF NOT EXISTS source_type ON TABLE source TYPE option<string>;
```

Domain model:
```python
class Source(ObjectModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    table_name: ClassVar[str] = "source"
    asset: Optional[Asset] = None
    title: Optional[str] = None
    topics: Optional[list[str]] = Field(default_factory=list)
    provenance: Optional[dict[str, Any]] = Field(default_factory=dict)
    source_type: Optional[
        Literal["link", "upload", "text", "web_import", "deep_research_report"]
    ] = None
    full_text: Optional[str] = None
    command: Optional[str | RecordID] = Field(default=None, ...)  # link to surreal-commands job
```
`Asset` helper: `class Asset(BaseModel): file_path: Optional[str]; url: Optional[str]`.

Methods: `vectorize()` (submits `embed_source` job, fire-and-forget, returns
command_id — NOT auto-called on save), `add_insight(type, content)` (submits
`create_insight` job), `get_insights()`, `get_context(short|long)`,
`get_status()` / `get_processing_progress()` (poll surreal-commands),
`get_embedded_chunks()`, `add_to_notebook()` (idempotent `reference` edge).

### 2.3 `source_embedding` (SCHEMAFULL) — vector chunks

Migration `1.surrealql`:
```surql
DEFINE TABLE IF NOT EXISTS source_embedding SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS source    ON TABLE source_embedding TYPE record<source>;
DEFINE FIELD IF NOT EXISTS order     ON TABLE source_embedding TYPE int;
DEFINE FIELD IF NOT EXISTS content   ON TABLE source_embedding TYPE string;
DEFINE FIELD IF NOT EXISTS embedding ON TABLE source_embedding TYPE array<float>;
```
HNSW vector index (migration `21.surrealql`):
`DEFINE INDEX source_embedding_hnsw ON source_embedding FIELDS embedding HNSW DIMENSION 768;`

Domain model (minimal — only `content` is declared; `source`/`order`/`embedding`
are written by the embed worker):
```python
class SourceEmbedding(ObjectModel):
    table_name: ClassVar[str] = "source_embedding"
    content: str
    # get_source() → parent Source via `fetch source`
```

### 2.4 `source_insight` (SCHEMAFULL) — derived AI insight

Migration `1.surrealql` (+ `10`/`13` make `embedding` optional):
```surql
DEFINE TABLE IF NOT EXISTS source_insight SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS source       ON TABLE source_insight TYPE record<source>;
DEFINE FIELD IF NOT EXISTS insight_type ON TABLE source_insight TYPE string;
DEFINE FIELD IF NOT EXISTS content      ON TABLE source_insight TYPE string;
DEFINE FIELD OVERWRITE     embedding    ON TABLE source_insight TYPE option<array<float>>;
```
HNSW index: `source_insight_hnsw ... DIMENSION 768` (migration 21).

Domain model:
```python
class SourceInsight(ObjectModel):
    table_name: ClassVar[str] = "source_insight"
    insight_type: str
    content: str
    # get_source(); save_as_note(notebook_id) → creates a Note from the insight
```

### 2.5 `note` (SCHEMAFULL) — human/AI note

Migration `1.surrealql` (+ `2` adds `note_type`, `10`/`13` make `embedding`
optional). **Note: the embedding is a column on the row — there is NO separate
`note_embedding` table** (a phantom table; audit D-1 removed dead cleanup code):
```surql
DEFINE TABLE IF NOT EXISTS note SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS title     ON TABLE note TYPE option<string>;
DEFINE FIELD IF NOT EXISTS summary   ON TABLE note TYPE option<string>;
DEFINE FIELD IF NOT EXISTS content   ON TABLE note TYPE option<string>;
DEFINE FIELD OVERWRITE     embedding ON TABLE note TYPE option<array<float>>;
DEFINE FIELD IF NOT EXISTS note_type ON TABLE note TYPE option<string>;   -- migration 2
DEFINE FIELD IF NOT EXISTS created ON note DEFAULT time::now() VALUE $before OR time::now();
DEFINE FIELD IF NOT EXISTS updated ON note DEFAULT time::now() VALUE time::now();
```
HNSW index: `note_hnsw ON note FIELDS embedding HNSW DIMENSION 768` (migration 21).

Domain model:
```python
class Note(ObjectModel):
    table_name: ClassVar[str] = "note"
    title: Optional[str] = None
    note_type: Optional[Literal["human", "ai"]] = None
    content: Optional[str] = None
    # content_must_not_be_empty validator
```
`Note.save()` **auto-submits an `embed_note` job** (fire-and-forget) if content
is non-empty and the command is registered in surreal-commands. `add_to_notebook`
creates an idempotent `artifact` edge. `get_context(short)` uses a token budget
(`_SHORT_CONTEXT_MAX_TOKENS = 160`) with an ellipsis, not a raw char slice.

### 2.6 `chat_session` (SCHEMALESS) — conversation container

Migration `3.surrealql` creates it; `8` adds `model_override`; `20` adds
`disabled_mcp_servers`:
```surql
DEFINE TABLE IF NOT EXISTS chat_session SCHEMALESS;
DEFINE FIELD IF NOT EXISTS model_override        ON chat_session TYPE option<string>;         -- migration 8
DEFINE FIELD IF NOT EXISTS disabled_mcp_servers  ON chat_session TYPE option<array<string>> DEFAULT NONE;  -- migration 20
```
Actual message history is NOT stored in this row — it lives in the **LangGraph
SQLite checkpointer** keyed by `thread_id == str(chat_session.id)`.

Domain model:
```python
class ChatSession(ObjectModel):
    table_name: ClassVar[str] = "chat_session"
    nullable_fields: ClassVar[set[str]] = {"model_override", "disabled_mcp_servers"}
    title: Optional[str] = None
    model_override: Optional[str] = None
    disabled_mcp_servers: Optional[list[str]] = None
    # relate_to_notebook() / relate_to_source() → idempotent refers_to edges
    # delete() sweeps refers_to edges first (v0.8.68)
```

### 2.7 `transformation` (SCHEMAFULL) — reusable prompt

Migration `5.surrealql`:
```surql
DEFINE TABLE IF NOT EXISTS transformation SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name          ON TABLE transformation TYPE string;
DEFINE FIELD IF NOT EXISTS title         ON TABLE transformation TYPE string;
DEFINE FIELD IF NOT EXISTS description   ON TABLE transformation TYPE string;
DEFINE FIELD IF NOT EXISTS prompt        ON TABLE transformation TYPE string;
DEFINE FIELD IF NOT EXISTS apply_default ON TABLE transformation TYPE bool DEFAULT False;
```
Migration 5 also seeds several default transformations (e.g. "Analyze Paper").

Domain model:
```python
class Transformation(ObjectModel):
    table_name: ClassVar[str] = "transformation"
    name: str
    title: str
    description: str
    prompt: str
    apply_default: bool
```
Two built-ins are lazily seeded on first use: `summarize` (name="summarize",
title="Summary") and `key_topics` (name="key_topics", title="Key Topics") — see
`get_or_create_summarize_transformation()` / `get_or_create_key_topics_transformation()`.

### 2.8 `model` (SCHEMALESS) — AI model registry

There is **no `DEFINE TABLE model`** — the table is created implicitly on first
insert (SCHEMALESS). Migration `6.surrealql` normalizes `provider='vertexai'` →
`'vertex'`; migration `12.surrealql` adds the credential link field:
```surql
-- migration 12:
DEFINE FIELD IF NOT EXISTS credential ON model TYPE option<record<credential>>;
```

Domain model (`open_notebook/ai/models.py`):
```python
class Model(ObjectModel):
    table_name: ClassVar[str] = "model"
    nullable_fields: ClassVar[set[str]] = {"credential"}
    name: str
    provider: str
    type: str                      # language | embedding | speech_to_text | text_to_speech
    credential: Optional[str] = None   # record<credential> link
    # get_models_by_type(), get_by_credential(), get_credential_obj()
    # delete() nulls out any DefaultModels field referencing this model
```

**`default_models` singleton** (`RecordModel`, `record_id =
open_notebook:default_models`). Migration 1 seeds `default_chat_model=""`;
migration 18 adds `auto_route_cloud`:
```python
class DefaultModels(RecordModel):
    record_id: ClassVar[str] = "open_notebook:default_models"
    default_chat_model: Optional[str] = None
    default_transformation_model: Optional[str] = None
    large_context_model: Optional[str] = None
    default_text_to_speech_model: Optional[str] = None
    default_speech_to_text_model: Optional[str] = None
    default_embedding_model: Optional[str] = None
    default_tools_model: Optional[str] = None
    default_reasoning_model: Optional[str] = None      # ONP v0.5 — slow/deep reasoning slot
    auto_route_cloud: Optional[str] = None             # migration 18 — smart-router cloud slot
    auto_route_enabled: Optional[bool] = False         # v0.8.37 UI toggle
    auto_route_provider_pref: Optional[str] = "auto"   # auto | local | cloud
    # get_instance() ALWAYS fetches fresh (bypasses singleton cache)
```

### 2.9 `episode_profile` (SCHEMAFULL) — podcast episode config

Migration `7.surrealql` (+ `14` adds model-registry refs + `language`):
```surql
DEFINE TABLE IF NOT EXISTS episode_profile SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name               ON TABLE episode_profile TYPE string;
DEFINE FIELD IF NOT EXISTS description        ON TABLE episode_profile TYPE option<string>;
DEFINE FIELD IF NOT EXISTS speaker_config     ON TABLE episode_profile TYPE string;
DEFINE FIELD OVERWRITE     outline_provider   ON TABLE episode_profile TYPE option<string>;   -- legacy (migration 14)
DEFINE FIELD OVERWRITE     outline_model      ON TABLE episode_profile TYPE option<string>;   -- legacy
DEFINE FIELD OVERWRITE     transcript_provider ON TABLE episode_profile TYPE option<string>;  -- legacy
DEFINE FIELD OVERWRITE     transcript_model   ON TABLE episode_profile TYPE option<string>;   -- legacy
DEFINE FIELD IF NOT EXISTS outline_llm        ON TABLE episode_profile TYPE option<record<model>>;    -- migration 14
DEFINE FIELD IF NOT EXISTS transcript_llm     ON TABLE episode_profile TYPE option<record<model>>;    -- migration 14
DEFINE FIELD IF NOT EXISTS language           ON TABLE episode_profile TYPE option<string>;            -- migration 14 (BCP 47)
DEFINE FIELD IF NOT EXISTS default_briefing   ON TABLE episode_profile TYPE string;
DEFINE FIELD IF NOT EXISTS num_segments       ON TABLE episode_profile TYPE int DEFAULT 5;
DEFINE INDEX IF NOT EXISTS idx_episode_profile_name ON TABLE episode_profile COLUMNS name UNIQUE CONCURRENTLY;
```
Migration 7 seeds three profiles: `tech_discussion`, `solo_expert`,
`business_analysis`.

Domain model (`open_notebook/podcasts/models.py`) — key fields:
```python
class EpisodeProfile(ObjectModel):
    table_name: ClassVar[str] = "episode_profile"
    name: str                          # unique
    description: Optional[str] = None
    speaker_config: str                # references a SpeakerProfile by name
    outline_llm: Optional[str] = None      # record<model>
    transcript_llm: Optional[str] = None   # record<model>
    language: Optional[str] = None         # BCP 47 (e.g. pt-BR)
    default_briefing: str
    num_segments: int = 5              # validated 3..20
    # resolve_outline_config()/resolve_transcript_config() → (provider, name, config)
```

### 2.10 `speaker_profile` (SCHEMAFULL) — podcast voices

Migration `7.surrealql` (+ `14` adds `voice_model` + per-speaker override):
```surql
DEFINE TABLE IF NOT EXISTS speaker_profile SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name        ON TABLE speaker_profile TYPE string;
DEFINE FIELD IF NOT EXISTS description ON TABLE speaker_profile TYPE option<string>;
DEFINE FIELD OVERWRITE     tts_provider ON TABLE speaker_profile TYPE option<string>;  -- legacy (migration 14)
DEFINE FIELD OVERWRITE     tts_model    ON TABLE speaker_profile TYPE option<string>;  -- legacy
DEFINE FIELD IF NOT EXISTS voice_model  ON TABLE speaker_profile TYPE option<record<model>>;   -- migration 14
DEFINE FIELD IF NOT EXISTS speakers     ON TABLE speaker_profile TYPE array<object>;
DEFINE FIELD IF NOT EXISTS speakers.*.name        ON TABLE speaker_profile TYPE string;
DEFINE FIELD IF NOT EXISTS speakers.*.voice_id    ON TABLE speaker_profile TYPE option<string>;
DEFINE FIELD IF NOT EXISTS speakers.*.backstory   ON TABLE speaker_profile TYPE option<string>;
DEFINE FIELD IF NOT EXISTS speakers.*.personality ON TABLE speaker_profile TYPE option<string>;
DEFINE FIELD IF NOT EXISTS speakers.*.voice_model ON TABLE speaker_profile TYPE option<record<model>>;  -- migration 14
DEFINE INDEX IF NOT EXISTS idx_speaker_profile_name ON TABLE speaker_profile COLUMNS name UNIQUE CONCURRENTLY;
```

Domain model:
```python
class SpeakerProfile(ObjectModel):
    table_name: ClassVar[str] = "speaker_profile"
    name: str
    description: Optional[str] = None
    voice_model: Optional[str] = None   # record<model>
    speakers: list[dict[str, Any]]      # 1..4 speakers, each requires
                                        # name/voice_id/backstory/personality
    # resolve_tts_config() → (provider, name, config)
```

### 2.11 `episode` (SCHEMAFULL) — generated podcast episode

Migration `7.surrealql` (+ `22` adds staged-generation fields):
```surql
DEFINE TABLE IF NOT EXISTS episode SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name             ON TABLE episode TYPE string;
DEFINE FIELD IF NOT EXISTS briefing         ON TABLE episode TYPE option<string>;
DEFINE FIELD IF NOT EXISTS episode_profile  ON TABLE episode FLEXIBLE TYPE object;
DEFINE FIELD IF NOT EXISTS speaker_profile  ON TABLE episode FLEXIBLE TYPE object;
DEFINE FIELD IF NOT EXISTS transcript       ON TABLE episode FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS outline          ON TABLE episode FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS command          ON TABLE episode TYPE option<record<command>>;
DEFINE FIELD IF NOT EXISTS content          ON TABLE episode TYPE option<string>;
DEFINE FIELD IF NOT EXISTS audio_file       ON TABLE episode TYPE option<string>;
-- migration 22 (staged generation):
DEFINE FIELD IF NOT EXISTS briefing_suffix  ON TABLE episode TYPE option<string>;
DEFINE FIELD IF NOT EXISTS generation_stage ON TABLE episode TYPE option<string>;
DEFINE FIELD IF NOT EXISTS cancel_requested ON TABLE episode TYPE option<bool>;
```
Profiles are stored as **object snapshots** (frozen at generation time), not
references. `generation_stage` ∈ {`generating_outline`, `generating_transcript`,
`generating_audio`, `combining_audio`, `awaiting_review`, `cancelled`}.

Domain model `PodcastEpisode` (`table_name = "episode"`,
`nullable_fields = {"generation_stage"}`): `name`, `episode_profile: dict`,
`speaker_profile: dict`, `briefing`, `briefing_suffix`, `content`,
`audio_file`, `transcript: dict`, `outline: dict`, `command`, `generation_stage`,
`cancel_requested`. `get_job_status()` / `get_job_detail()` poll surreal-commands.

### 2.12 `credential` (SCHEMAFULL) — encrypted provider credentials

Migration `12.surrealql`:
```surql
DEFINE TABLE IF NOT EXISTS credential SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name               ON credential TYPE string;
DEFINE FIELD IF NOT EXISTS provider           ON credential TYPE string;
DEFINE FIELD IF NOT EXISTS modalities         ON credential TYPE array DEFAULT [];
DEFINE FIELD IF NOT EXISTS modalities.*        ON credential TYPE string;
DEFINE FIELD IF NOT EXISTS api_key            ON credential TYPE option<string>;   -- Fernet-encrypted
DEFINE FIELD IF NOT EXISTS base_url           ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS endpoint           ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS api_version        ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS endpoint_llm       ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS endpoint_embedding ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS endpoint_stt       ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS endpoint_tts       ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS project            ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS location           ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS credentials_path   ON credential TYPE option<string>;
DEFINE INDEX IF NOT EXISTS idx_credential_provider ON credential FIELDS provider;
```
Migration `15.surrealql` note references a flexible `config` object addition in
some builds; the current domain model exposes the discrete fields above.

Domain model (`open_notebook/domain/credential.py`):
```python
class Credential(ObjectModel):
    table_name: ClassVar[str] = "credential"
    nullable_fields: ClassVar[set[str]] = {
        "api_key","base_url","endpoint","api_version","endpoint_llm",
        "endpoint_embedding","endpoint_stt","endpoint_tts","project",
        "location","credentials_path",
    }
    name: str
    provider: str
    modalities: list[str] = []
    api_key: Optional[SecretStr] = None      # NEVER returned raw by the API
    decryption_error: Optional[str] = None   # transient (not persisted)
    base_url / endpoint / api_version / endpoint_llm / endpoint_embedding
    endpoint_stt / endpoint_tts / project / location / credentials_path: Optional[str]
```
**Encryption**: `_prepare_save_data()` extracts the `SecretStr` and
`encrypt_value()`s it (Fernet, key derived by SHA-256 from
`OPEN_NOTEBOOK_ENCRYPTION_KEY`; rotation via `OPEN_NOTEBOOK_ENCRYPTION_KEYS`,
comma-separated, primary first, `MultiFernet` for decrypt). `get()` / `get_all()`
are overridden to `decrypt_value()` on read; a decryption failure yields a
placeholder credential with `decryption_error` set (never crashes the list).
`to_esperanto_config()` builds the config dict passed to Esperanto AIFactory.

### 2.13 `content_settings` singleton (`open_notebook:content_settings`)

`RecordModel` (`open_notebook/domain/content_settings.py`) — no dedicated
migration DEFINE; stored as a singleton config record:
```python
class ContentSettings(RecordModel):
    record_id: ClassVar[str] = "open_notebook:content_settings"
    default_content_processing_engine_doc: Optional[Literal["auto","docling","simple"]] = "auto"
    default_content_processing_engine_url: Optional[
        Literal["auto","crawl4ai","firecrawl","jina","simple"]] = "auto"
    default_embedding_option: Optional[Literal["ask","always","never"]] = "ask"
    auto_delete_files: Optional[Literal["yes","no"]] = "yes"
    youtube_preferred_languages: Optional[list[str]] = ["en","pt","es","de","nl","en-GB","fr","de","hi","ja"]
    offline_mode: Optional[bool] = False                  # v0.8.68 force-offline
    auto_summarize_on_ingest: Optional[bool] = False      # v0.8.88
    auto_extract_topics_on_ingest: Optional[bool] = False # v0.8.91
```

Other singletons: `default_prompts` (`open_notebook:default_prompts`, one field
`transformation_instructions`).

### 2.14 Studio artifact tables (Evidence Studio)

Migration `23.surrealql` (`studio_artifact`) and `24.surrealql`
(`studio_workflow_run`). `studio_artifact` fields: `notebook_id record<notebook>`,
`artifact_type string`, `title string`, `status string DEFAULT "pending"`,
`source_ids array<record<source>>`, `prompt`, `model_id`, `provider`,
`output_format`, `output_payload FLEXIBLE object`, `citations FLEXIBLE array<object>`,
`export_paths FLEXIBLE object`, `revision_of_id record<studio_artifact>`.
Indexes on `notebook_id`, `status`, `artifact_type`. Domain models
`StudioArtifact` / `StudioWorkflowRun` live in `domain/notebook.py`.
`StudioArtifactType` literal includes report/study_guide/course_pack/briefing/
faq/flashcards/quiz/data_table/mind_map/timeline/infographic/slide_deck/
podcast_outline/podcast_audio/research_run.

### 2.15 Auxiliary tables

- **`mcp_server`** (migration 17, SCHEMAFULL): `name string` (UNIQUE),
  `url string`, `enabled bool DEFAULT true`, `priority int DEFAULT 100`
  (migration 19). DB-backed MCP registry the chat graph reads.
- **`gmail_integration`** (migration 16, SCHEMAFULL): encrypted OAuth token
  fields (`client_id_enc`, `client_secret_enc`, `access_token_enc`,
  `refresh_token_enc`), `token_expires_at`, `email_address`, `enabled`,
  `frequency` (daily|weekly|manual), `include_*` digest toggles, `last_sent_at`.
  Single record per install (single-user).
- **`memory_fact` / `memory_preference` / `memory_episode`** (migration 15,
  SCHEMAFULL, identical shape): `text string`, `embedding array<float>`,
  `metadata object`, `scope string DEFAULT "user"`, `confidence float DEFAULT 1.0`,
  `created_at datetime`. Each has `HNSW DIMENSION 768` index (nomic-embed-text-v1.5).
- **`podcast_config`** (migration 1, SCHEMALESS): legacy podcast config.
- **`_sbl_migrations`**: migration version-tracking table (see §4).
- **`open_notebook:provider_configs`** (migration 11): legacy ProviderConfig
  singleton, retained only for migration to the `credential` table.

---

## 3. Edge / relation tables

SurrealDB `TYPE RELATION` tables. Direction is **`in` → `out`** and is
easy to invert — the codebase repeatedly warns about this. All three are created
in migrations 1 and 3.

| Edge | Direction (`FROM in → TO out`) | Meaning | Created |
|------|-------------------------------|---------|---------|
| `reference` | `source → notebook` | a source is attached to a notebook | migration 1 |
| `artifact`  | `note → notebook`   | a note belongs to a notebook | migration 1 |
| `refers_to` | `chat_session → notebook\|source` | a chat session is scoped to a notebook or source | migration 3 (broadened to `notebook\|source` in migration 8) |

```surql
-- migration 1
DEFINE TABLE IF NOT EXISTS reference TYPE RELATION FROM source TO notebook;
DEFINE TABLE IF NOT EXISTS artifact  TYPE RELATION FROM note   TO notebook;
-- migration 3
DEFINE TABLE IF NOT EXISTS refers_to TYPE RELATION FROM chat_session TO notebook;
-- migration 8
DEFINE TABLE OVERWRITE     refers_to TYPE RELATION FROM chat_session TO notebook|source;
```

### 3.1 Direction semantics in queries

The **notebook** is always the `out` side of `reference`/`artifact`; the source
or note is the `in` side. Canonical traversals (`domain/notebook.py`):

```python
# sources of a notebook: in = source, out = notebook
"select in as source from reference where out=$id fetch source"
# notes of a notebook: in = note, out = notebook
"select in as note from artifact where out=$id fetch note"
# chat sessions of a notebook: in = chat_session, out = notebook
"select <- chat_session as chat_session from refers_to where out=$id fetch chat_session"
```

### 3.2 Edge creation is NOT upsert — dedup is manual

SurrealDB `RELATE` always creates a new edge. Every relate path guards for an
existing edge first (idempotency), because a duplicate edge inflates
source/note counts:

```python
# Source.add_to_notebook (reference edge)
existing = await repo_query(
    "SELECT * FROM reference WHERE out = $notebook_id AND in = $source_id", ...)
if existing: return existing[0]
return await self.relate("reference", notebook_id)
```
`Note.add_to_notebook` (artifact) and `ChatSession.relate_to_notebook` /
`relate_to_source` (refers_to) follow the same pattern (v0.8.66 D-3).

---

## 4. Migrations

### 4.1 Files

Location: `open_notebook/database/migrations/` — pairs of `N.surrealql` (up) and
optional `N_down.surrealql` (down). The current set runs **1 → 25**.

| # | Adds |
|---|------|
| 1 | Core tables (source, source_embedding, source_insight, note, notebook), reference/artifact edges, analyzer + BM25 indexes, `fn::text_search`, `fn::vector_search`, `podcast_config`, seeds `default_models` |
| 2 | `note.note_type` |
| 3 | `chat_session`, `refers_to` edge, refined `fn::vector_search`/`fn::text_search` (add `min_similarity`, highlight columns) |
| 4 | Rewrites search functions (parent_id, highlight) |
| 5 | `transformation` table + seed default transformations |
| 6 | Normalize `model.provider` vertexai→vertex |
| 7 | `episode_profile`, `speaker_profile`, `episode` + seed profiles |
| 8 | `refers_to` → `notebook\|source`; `chat_session.model_override`; `source.command` |
| 9 | Refine `fn::vector_search` (dimension/None guards) |
| 10 | Insight/embedding source indexes; make embeddings optional; delete orphans |
| 11 | Legacy `provider_configs` singleton |
| 12 | `credential` table + `model.credential` link |
| 13 | `source_insight.embedding` / `note.embedding` → optional |
| 14 | Podcast model-registry refs (`outline_llm`, `transcript_llm`, `voice_model`), `episode_profile.language`, per-speaker override |
| 15 | Memory tables (`memory_fact`/`memory_preference`/`memory_episode`), HNSW dim 768; credential `config` object |
| 16 | `gmail_integration` |
| 17 | `mcp_server` registry |
| 18 | `default_models.auto_route_cloud` |
| 19 | `mcp_server.priority` |
| 20 | `chat_session.disabled_mcp_servers` |
| 21 | HNSW vector indexes + KNN `<|100|>` operator in `fn::vector_search` |
| 22 | `episode` staged-generation fields (`briefing_suffix`, `generation_stage`, `cancel_requested`) |
| 23 | `studio_artifact` |
| 24 | `studio_workflow_run` |
| 25 | `source.provenance`, `source.source_type` |

Migrations are **re-run-safe**: nearly all `DEFINE` use `IF NOT EXISTS`
(or `OVERWRITE` where a redefine is intended).

### 4.2 `AsyncMigrationManager` (`database/async_migrate.py`)

- **Auto-discovery** (`_discover_migrations`): scans the migrations dir, parses
  `N` / `N_down`, and builds parallel `ups`/`downs` lists indexed by version.
  It **enforces contiguous numbering 1..N** — a gap raises `RuntimeError` rather
  than silently mis-numbering.
- `get_latest_version()` reads `MAX(version)` from `_sbl_migrations` (returns 0
  if the table is missing → fresh-install bootstrap).
- `needs_migration()` = `current_version < len(up_migrations)`.
- `run_migration_up()` → `runner.run_all()` runs every pending up migration and
  bumps the version after each. `bump_version()` does
  `CREATE type::thing('_sbl_migrations', $version) SET version=$version, applied_at=time::now()`.
- `AsyncMigration.from_file()` strips `--` comments and blank lines and joins
  into one statement string; `run(bump)` executes it inside `db_connection()`.
- Called from the FastAPI **lifespan** handler on startup (see doc 04). A sync
  wrapper `MigrationManager` (`migrate.py`) exists for legacy call sites.

### 4.3 Search functions (defined in migrations)

- `fn::text_search($query_text, $match_count, $sources, $show_notes)` — BM25 over
  source titles/full_text, source_embedding chunks, insights, and note
  title/content; uses `search::highlight('`','`',1)` and `search::score(1)`.
- `fn::vector_search($query, $match_count, $sources, $show_notes, $min_similarity)`
  — HNSW KNN (`embedding <|100|> $query`) + `vector::similarity::cosine`
  thresholded at `$min_similarity`, grouped by parent id.

Domain wrappers (`domain/notebook.py`): `text_search(keyword, results, source,
note)` and `vector_search(keyword, results, source, note, minimum_score)`.
`text_search` **falls back to `vector_search`** on a `search::highlight`
"position overflow" (large/multi-byte chunks), and raises
`DatabaseOperationError` if that also fails (never silently returns empty).
Default vector floor `_DEFAULT_VECTOR_MIN_SCORE = 0.3` (env-tunable via
`ONP_VECTOR_MIN_SCORE`, clamped to [0,1]).

---

## 5. Delete-cascade behavior

Cascades are enforced in the **domain layer** (Python), not by DB triggers —
except one legacy DB event. Because edges are not auto-cleaned, every delete
sweeps its edges to prevent `fetch` producing `null` rows that crash
`Model(**None)`.

### 5.1 DB-level event (migration 1)
```surql
DEFINE EVENT source_delete ON TABLE source WHEN ($after == NONE) THEN {
    delete source_embedding where source == $before.id;
    delete source_insight  where source == $before.id;
};
```
The domain `Source.delete()` also performs these deletes explicitly (belt-and-
suspenders), so cleanup happens regardless of event firing.

### 5.2 `Source.delete()` (`domain/notebook.py`)
1. **Cancel in-flight command** first (if `command` status ∈ {new,running,queued})
   via `surreal_commands` — prevents the embed worker racing to write embeddings
   on a deleted source (v0.7.32).
2. **Unlink the file** only if inside `UPLOADS_FOLDER` (SSRF/path-traversal
   guard, v0.6.34).
3. `DELETE source_embedding WHERE source=$id`, `DELETE source_insight WHERE
   source=$id`, `DELETE reference WHERE in=$id` (unlink from all notebooks).
4. `super().delete()` (remove the row).
5. **Race-window post-sweep** (v0.7.133): re-run the embedding/insight deletes
   *after* the row delete, since the cancel doesn't actually stop the worker.

### 5.3 `Note.delete()`
`DELETE artifact WHERE in=$note_id` first (unlink), then `super().delete()`.
Embedding is a column on the note row, so it goes with the row (no
`note_embedding` table exists — audit D-1).

### 5.4 `ChatSession.delete()` (v0.8.68)
`DELETE refers_to WHERE in=$sid` (sweep edges) then `super().delete()`.
Best-effort; never blocks the primary delete.

### 5.5 `Notebook.delete(delete_exclusive_sources=False)` — the big cascade
Returns `{deleted_notes, deleted_sources, unlinked_sources,
deleted_chat_session_ids}`.
1. **Notes**: gather all linked notes; for ≤ `ONP_NOTEBOOK_DELETE_BULK_THRESHOLD`
   (default 25) delete concurrently via `asyncio.gather(return_exceptions=True)`;
   above the threshold use `_bulk_delete_notes()` (2 statements:
   `DELETE note WHERE id IN $ids`, then `DELETE artifact WHERE in IN $ids`).
2. `DELETE artifact WHERE out=$notebook_id` (unlink any orphan note edges).
3. **Sources**: if `delete_exclusive_sources`, delete sources whose `reference`
   edges point to no other notebook (`assigned_others == 0`), else just count.
   Always `DELETE reference WHERE out=$notebook_id` (unlink all).
4. **Chat sessions**: capture their ids, `DELETE refers_to WHERE out=$notebook_id`
   then `DELETE chat_session WHERE id IN $ids`. The ids are **returned to the API
   layer** so it can delete each session's LangGraph SQLite checkpoint thread
   (`thread_id == str(session_id)`); the domain layer must not import the
   checkpointer (layering) — v0.8.48.
5. `super().delete()` removes the notebook row.

`get_delete_preview()` returns `{note_count, exclusive_source_count,
shared_source_count}` for a confirmation dialog, computed via
`count(->reference[WHERE out != $notebook_id])`.

### 5.6 `Model.delete()`
Nulls out every `default_models` field that referenced this model (so lookups
fall through to the handled "no model configured" path), warn-logs any
episode/speaker profile still referencing it (not auto-cleared), then
`super().delete()`.

**No cascade**: deleting an `episode_profile` / `speaker_profile` does NOT touch
`episode` rows (episodes store profile snapshots, not references).

---

## 6. Vector-embedding storage summary

| What | Where | Dimension | Index |
|------|-------|-----------|-------|
| Source chunks | `source_embedding.embedding` (`array<float>`) | 768 | HNSW `source_embedding_hnsw` |
| Source insights | `source_insight.embedding` (`option<array<float>>`) | 768 | HNSW `source_insight_hnsw` |
| Notes | `note.embedding` (`option<array<float>>`) — column, no separate table | 768 | HNSW `note_hnsw` |
| Memory (fact/pref/episode) | `memory_*.embedding` | 768 | HNSW `memory_*_embedding` |

Dimension **768** matches `nomic-embed-text-v1.5`. Embeddings are generated
fire-and-forget via surreal-commands (`embed_source`, `embed_note`,
`embed_insight`) — see doc 08. Similarity is cosine
(`vector::similarity::cosine`), with a KNN pre-filter (`<|100|>`) added in
migration 21.

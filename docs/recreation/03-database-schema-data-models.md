# 03 — Database Schema & Data Models

> Recreation documentation for **Open Notebook Plus**. This document describes the
> complete SurrealDB schema (from `open_notebook/database/migrations/*.surrealql`),
> the edge/relation tables, the Pydantic domain models, indexes, and the
> `AsyncMigrationManager`. Companion docs:
> [`01-project-overview-architecture.md`](./01-project-overview-architecture.md),
> [`02-environment-setup-dependencies.md`](./02-environment-setup-dependencies.md).
>
> **Secrets policy:** API keys live in the `credential` table **encrypted at
> rest** (Fernet). Never store or document plaintext keys; use `<YOUR_KEY>`.

---

## 1. Database engine model

The store is **SurrealDB v2** — a single engine combining graph relations,
schema-full/schema-less documents, native vector search, BM25 full-text search,
and KV. Connection is over WebSocket RPC (`ws://host:8000/rpc`) using the
`surrealdb` Python `AsyncSurreal` client, namespace `open_notebook`, database
`open_notebook` (or `production` in the desktop bundle).

All SQL is SurrealQL. There is **no ORM**; domain models map to tables through
the repository layer (`open_notebook/database/repository.py`).

---

## 2. Migration system (`AsyncMigrationManager`)

Source: `open_notebook/database/async_migrate.py`. Migrations are plain
`.surrealql` files numbered `1..N` in
`open_notebook/database/migrations/`, each optionally paired with `<n>_down.surrealql`.

### Discovery & ordering

`AsyncMigrationManager._discover_migrations()` scans the migrations directory at
construction time and builds two parallel lists (ups, downs) indexed by version.
Key invariants enforced (from the code comments):

- **Contiguous numbering** — a gap (e.g. missing `4.surrealql` between `3` and
  `5`) raises `RuntimeError` rather than silently mis-numbering versions. This
  replaced an earlier hard-coded `1..N` list.
- **Parallel down list** — `down_migrations[i]` is `None` if `<n>_down.surrealql`
  is absent; `run_one_down` guards against missing entries instead of
  `IndexError`-ing.

```python
class AsyncMigrationManager:
    def __init__(self):
        self.up_migrations, self.down_migrations = self._discover_migrations()
        self.runner = AsyncMigrationRunner(
            up_migrations=self.up_migrations,
            down_migrations=self.down_migrations,
        )

    async def needs_migration(self) -> bool:
        return await self.get_current_version() < len(self.up_migrations)

    async def run_migration_up(self):
        if await self.needs_migration():
            await self.runner.run_all()
```

### Version tracking

Versions are recorded in the `_sbl_migrations` table:

```python
async def bump_version() -> None:
    current_version = await get_latest_version()
    new_version = current_version + 1
    await repo_query(
        "CREATE type::thing('_sbl_migrations', $version) "
        "SET version = $version, applied_at = time::now();",
        {"version": new_version},
    )
```

`get_latest_version()` returns `max(version)` from `_sbl_migrations`, or `0` if
the table is missing (the fresh-install bootstrap case). `get_all_versions()`
classifies errors: a missing table logs at DEBUG (bootstrap), any other error
logs at WARNING (could otherwise re-run every migration on a transient failure).

### When migrations run

The FastAPI `lifespan` handler (`api/main.py:237`) constructs the manager and
calls `run_migration_up()` on startup, then runs the podcast data migration
(`migrate_podcast_profiles()`). A sync wrapper `MigrationManager` exists in
`migrate.py` for legacy callers.

### Loading & sanitizing files

`AsyncMigration.from_file()` reads a `.surrealql` file, strips comment lines
(`--`) and blank lines, and joins the rest with spaces into a single statement
batch executed via `connection.query(sql)`.

---

## 3. Migration-by-migration schema

Below is what each migration file defines. Files are in
`open_notebook/database/migrations/`.

### Migration 1 — core content tables, search, default models

Defines the foundational tables and the search functions.

```sql
-- source: a content item (file / URL / text)
DEFINE TABLE IF NOT EXISTS source SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS asset ON TABLE source FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS title ON TABLE source TYPE option<string>;
DEFINE FIELD IF NOT EXISTS topics ON TABLE source TYPE option<array<string>>;
DEFINE FIELD IF NOT EXISTS full_text ON TABLE source TYPE option<string>;
DEFINE FIELD IF NOT EXISTS created ON source DEFAULT time::now() VALUE $before OR time::now();
DEFINE FIELD IF NOT EXISTS updated ON source DEFAULT time::now() VALUE time::now();

-- source_embedding: chunked vector store for a source
DEFINE TABLE IF NOT EXISTS source_embedding SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS source    ON TABLE source_embedding TYPE record<source>;
DEFINE FIELD IF NOT EXISTS order     ON TABLE source_embedding TYPE int;
DEFINE FIELD IF NOT EXISTS content   ON TABLE source_embedding TYPE string;
DEFINE FIELD IF NOT EXISTS embedding ON TABLE source_embedding TYPE array<float>;

-- source_insight: derived insight (transformation output) for a source
DEFINE TABLE IF NOT EXISTS source_insight SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS source       ON TABLE source_insight TYPE record<source>;
DEFINE FIELD IF NOT EXISTS insight_type ON TABLE source_insight TYPE string;
DEFINE FIELD IF NOT EXISTS content      ON TABLE source_insight TYPE string;
DEFINE FIELD IF NOT EXISTS embedding    ON TABLE source_insight TYPE array<float>;

-- delete cascade: removing a source removes its embeddings + insights
DEFINE EVENT IF NOT EXISTS source_delete ON TABLE source WHEN ($after == NONE) THEN {
    delete source_embedding where source == $before.id;
    delete source_insight  where source == $before.id;
};

-- note: standalone or notebook-linked note
DEFINE TABLE IF NOT EXISTS note SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS title     ON TABLE note TYPE option<string>;
DEFINE FIELD IF NOT EXISTS summary   ON TABLE note TYPE option<string>;
DEFINE FIELD IF NOT EXISTS content   ON TABLE note TYPE option<string>;
DEFINE FIELD IF NOT EXISTS embedding ON TABLE note TYPE array<float>;

-- notebook: research project container
DEFINE TABLE IF NOT EXISTS notebook SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name        ON TABLE notebook TYPE option<string>;
DEFINE FIELD IF NOT EXISTS description ON TABLE notebook TYPE option<string>;
DEFINE FIELD IF NOT EXISTS archived    ON TABLE notebook TYPE option<bool> DEFAULT False;

-- EDGE TABLES (graph relations)
DEFINE TABLE IF NOT EXISTS reference TYPE RELATION FROM source TO notebook;
DEFINE TABLE IF NOT EXISTS artifact  TYPE RELATION FROM note   TO notebook;

DEFINE TABLE IF NOT EXISTS podcast_config SCHEMALESS;

-- full-text analyzer + BM25 indexes
DEFINE ANALYZER IF NOT EXISTS my_analyzer
    TOKENIZERS blank,class,camel,punct FILTERS snowball(english), lowercase;
DEFINE INDEX IF NOT EXISTS idx_source_title      ON TABLE source         COLUMNS title     SEARCH ANALYZER my_analyzer BM25 HIGHLIGHTS;
DEFINE INDEX IF NOT EXISTS idx_source_full_text  ON TABLE source         COLUMNS full_text SEARCH ANALYZER my_analyzer BM25 HIGHLIGHTS;
DEFINE INDEX IF NOT EXISTS idx_source_embed_chunk ON TABLE source_embedding COLUMNS content  SEARCH ANALYZER my_analyzer BM25 HIGHLIGHTS;
DEFINE INDEX IF NOT EXISTS idx_source_insight    ON TABLE source_insight COLUMNS content    SEARCH ANALYZER my_analyzer BM25 HIGHLIGHTS;
DEFINE INDEX IF NOT EXISTS idx_note              ON TABLE note           COLUMNS content    SEARCH ANALYZER my_analyzer BM25 HIGHLIGHTS;
DEFINE INDEX IF NOT EXISTS idx_note_title        ON TABLE note           COLUMNS title      SEARCH ANALYZER my_analyzer BM25 HIGHLIGHTS;

-- fn::text_search(...) and fn::vector_search(...) defined here (see §5)
-- seed singleton:
IF array::len(select * from open_notebook:default_models) == 0 THEN
    CREATE open_notebook:default_models SET default_chat_model = ""
END;
```

> **Edge-table direction (critical):** `reference` is `FROM source TO notebook`
> — so `in` = source, `out` = notebook. `Notebook.get_sources()` queries
> `select in as source from reference where out=$id`. `artifact` is
> `FROM note TO notebook` (`in` = note, `out` = notebook). Inverting `in`/`out`
> is a documented recurring bug class in this codebase.

### Migration 2 — note typing

```sql
DEFINE FIELD IF NOT EXISTS note_type ON TABLE note TYPE option<string>;
```

### Migration 3 — chat sessions + `refers_to` edge + richer search

```sql
DEFINE TABLE IF NOT EXISTS chat_session SCHEMALESS;
DEFINE TABLE IF NOT EXISTS refers_to TYPE RELATION FROM chat_session TO notebook;
-- Redefines fn::vector_search with a $min_similarity arg and returns
--   id, title, content, parent_id, similarity
-- Redefines fn::text_search to return id/title/content/parent_id/relevance
```

### Migration 4 — search function refinements

Re-defines `fn::text_search` and `fn::vector_search` (fixes `id`/`parent_id`
selection, adds `array::flatten(content) as matches` to vector results).

### Migration 5 — transformations + default prompts

```sql
DEFINE TABLE IF NOT EXISTS transformation SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name          ON TABLE transformation TYPE string;
DEFINE FIELD IF NOT EXISTS title         ON TABLE transformation TYPE string;
DEFINE FIELD IF NOT EXISTS description   ON TABLE transformation TYPE string;
DEFINE FIELD IF NOT EXISTS prompt        ON TABLE transformation TYPE string;
DEFINE FIELD IF NOT EXISTS apply_default ON TABLE transformation TYPE bool DEFAULT False;
-- seeds 6 default transformations: Analyze Paper, Key Insights,
--   Dense Summary (apply_default: True), Reflections, Table of Contents,
--   Simple Summary
-- UPSERT open_notebook:default_prompts CONTENT { transformation_instructions: "..." }
```

### Migration 6 — data fix

```sql
update model set provider='vertex' where provider='vertexai';
```

### Migration 7 — podcast tables

Defines `episode_profile`, `speaker_profile`, and `episode` (see §4 and §6 for
full field lists), plus indexes and seed data (`tech_experts`, `solo_expert`,
`business_panel` speaker profiles; `tech_discussion`, `solo_expert`,
`business_analysis` episode profiles).

```sql
DEFINE TABLE IF NOT EXISTS episode SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name            ON TABLE episode TYPE string;
DEFINE FIELD IF NOT EXISTS briefing        ON TABLE episode TYPE option<string>;
DEFINE FIELD IF NOT EXISTS episode_profile ON TABLE episode FLEXIBLE TYPE object;
DEFINE FIELD IF NOT EXISTS speaker_profile ON TABLE episode FLEXIBLE TYPE object;
DEFINE FIELD IF NOT EXISTS transcript      ON TABLE episode FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS outline         ON TABLE episode FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS command         ON TABLE episode TYPE option<record<command>>;
DEFINE FIELD IF NOT EXISTS content         ON TABLE episode TYPE option<string>;
DEFINE FIELD IF NOT EXISTS audio_file      ON TABLE episode TYPE option<string>;
DEFINE INDEX IF NOT EXISTS idx_episode_profile_name ON TABLE episode_profile COLUMNS name UNIQUE CONCURRENTLY;
DEFINE INDEX IF NOT EXISTS idx_speaker_profile_name ON TABLE speaker_profile COLUMNS name UNIQUE CONCURRENTLY;
```

### Migration 8 — broaden chat target + per-session model override

```sql
DEFINE TABLE OVERWRITE refers_to TYPE RELATION FROM chat_session TO notebook|source;
DEFINE FIELD IF NOT EXISTS model_override ON chat_session TYPE option<string>;
DEFINE FIELD IF NOT EXISTS command        ON source       TYPE option<record<command>>;
```

> `refers_to` now points a `chat_session` at **either** a `notebook` or a
> `source`, enabling source-scoped chat.

### Migration 9 — vector search null-guard

Redefines `fn::vector_search` to skip rows where `embedding` is `none` or whose
length differs from the query (`array::len(embedding)=array::len($query)`),
preventing dimension-mismatch errors.

### Migration 10 — performance indexes + orphan cleanup

```sql
DEFINE INDEX IF NOT EXISTS idx_source_insight_source   ON source_insight   FIELDS source CONCURRENTLY;
DEFINE INDEX IF NOT EXISTS idx_source_embedding_source ON source_embedding FIELDS source CONCURRENTLY;
DEFINE FIELD OVERWRITE embedding ON TABLE source_insight TYPE option<array<float>>;
DEFINE FIELD OVERWRITE embedding ON TABLE note           TYPE option<array<float>>;
DELETE from source_embedding WHERE source.id=NONE;   -- orphans
DELETE from source_insight   WHERE source.id=NONE;
```

### Migration 11 — provider config singleton (legacy)

```sql
UPSERT open_notebook:provider_configs CONTENT { credentials: {} };
```

### Migration 12 — `credential` table + model→credential link

```sql
DEFINE TABLE IF NOT EXISTS credential SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name       ON credential TYPE string;
DEFINE FIELD IF NOT EXISTS provider   ON credential TYPE string;
DEFINE FIELD IF NOT EXISTS modalities ON credential TYPE array DEFAULT [];
DEFINE FIELD IF NOT EXISTS modalities.* ON credential TYPE string;
DEFINE FIELD IF NOT EXISTS api_key    ON credential TYPE option<string>;   -- ENCRYPTED at rest
DEFINE FIELD IF NOT EXISTS base_url   ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS endpoint   ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS api_version ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS endpoint_llm       ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS endpoint_embedding ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS endpoint_stt       ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS endpoint_tts       ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS project          ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS location         ON credential TYPE option<string>;
DEFINE FIELD IF NOT EXISTS credentials_path ON credential TYPE option<string>;
DEFINE INDEX IF NOT EXISTS idx_credential_provider ON credential FIELDS provider;
DEFINE FIELD IF NOT EXISTS credential ON model TYPE option<record<credential>>;
```

> The `model` table itself is **schema-less** (records created via the repository
> layer by the `Model` domain class, `table_name = "model"`). Migration 12 only
> adds the typed `credential` reference field onto it.

### Migration 13 — make derived embeddings optional

```sql
DEFINE FIELD OVERWRITE embedding ON TABLE source_insight TYPE option<array<float>>;
DEFINE FIELD OVERWRITE embedding ON TABLE note           TYPE option<array<float>>;
```

### Migration 14 — podcast profiles → model registry

Makes legacy provider/model string fields optional and adds `record<model>`
references + `language`:

```sql
DEFINE FIELD IF NOT EXISTS outline_llm    ON TABLE episode_profile TYPE option<record<model>>;
DEFINE FIELD IF NOT EXISTS transcript_llm ON TABLE episode_profile TYPE option<record<model>>;
DEFINE FIELD IF NOT EXISTS language       ON TABLE episode_profile TYPE option<string>;
DEFINE FIELD IF NOT EXISTS voice_model    ON TABLE speaker_profile TYPE option<record<model>>;
DEFINE FIELD IF NOT EXISTS speakers.*.voice_model ON TABLE speaker_profile TYPE option<record<model>>;
```

### Migration 15 — memory layer (3 tables, HNSW 768)

```sql
DEFINE TABLE IF NOT EXISTS memory_fact SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS text       ON memory_fact TYPE string;
DEFINE FIELD IF NOT EXISTS embedding  ON memory_fact TYPE array<float>;
DEFINE FIELD IF NOT EXISTS metadata   ON memory_fact TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS scope      ON memory_fact TYPE string DEFAULT "user";
DEFINE FIELD IF NOT EXISTS confidence ON memory_fact TYPE float  DEFAULT 1.0;
DEFINE FIELD IF NOT EXISTS created_at ON memory_fact TYPE datetime DEFAULT time::now();
DEFINE INDEX IF NOT EXISTS memory_fact_embedding ON memory_fact FIELDS embedding HNSW DIMENSION 768;
-- memory_preference and memory_episode have the IDENTICAL shape + HNSW index
```

The three tables (`memory_fact`, `memory_preference`, `memory_episode`) are
routed by a `kind` field in payloads. `DIMENSION 768` matches
`nomic-embed-text-v1.5`.

### Migration 16 — Gmail digest integration

```sql
DEFINE TABLE IF NOT EXISTS gmail_integration SCHEMAFULL;
-- encrypted OAuth fields: client_id_enc, client_secret_enc,
--   access_token_enc, refresh_token_enc, token_expires_at, email_address
-- prefs: enabled (bool), frequency ("daily"|"weekly"|"manual"),
--   include_notebooks/sources/notes/podcasts/memory (bool),
--   last_sent_at, created_at, updated_at
```

Single record per installation (ONP is single-user).

### Migration 17 — MCP server registry

```sql
DEFINE TABLE IF NOT EXISTS mcp_server SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS name    ON mcp_server TYPE string;
DEFINE FIELD IF NOT EXISTS url     ON mcp_server TYPE string;
DEFINE FIELD IF NOT EXISTS enabled ON mcp_server TYPE bool DEFAULT true;
DEFINE INDEX IF NOT EXISTS mcp_server_name_unique ON mcp_server FIELDS name UNIQUE;
```

### Migration 18 — smart-router cloud slot

```sql
DEFINE FIELD IF NOT EXISTS auto_route_cloud ON open_notebook TYPE option<string> DEFAULT NONE;
```

A dedicated cloud-model slot separate from `default_chat_model` so the router
doesn't silently fall back to a local model.

### Migration 19 — MCP server priority

```sql
DEFINE FIELD IF NOT EXISTS priority ON mcp_server TYPE int DEFAULT 100;
```

### Migration 20 — per-conversation MCP disable list

```sql
DEFINE FIELD IF NOT EXISTS disabled_mcp_servers ON chat_session TYPE option<array<string>> DEFAULT NONE;
```

### Migration 21 — HNSW vector indexes + KNN search

```sql
DEFINE INDEX IF NOT EXISTS source_embedding_hnsw ON source_embedding FIELDS embedding HNSW DIMENSION 768;
DEFINE INDEX IF NOT EXISTS source_insight_hnsw    ON source_insight   FIELDS embedding HNSW DIMENSION 768;
DEFINE INDEX IF NOT EXISTS note_hnsw              ON note             FIELDS embedding HNSW DIMENSION 768;
-- redefines fn::vector_search to use the KNN operator `embedding <|100|> $query`
-- in addition to the cosine-similarity filter (brute-force O(N) → indexed)
```

### Migration 22 — staged podcast generation fields

```sql
DEFINE FIELD IF NOT EXISTS briefing_suffix  ON TABLE episode TYPE option<string>;
DEFINE FIELD IF NOT EXISTS generation_stage ON TABLE episode TYPE option<string>;
DEFINE FIELD IF NOT EXISTS cancel_requested ON TABLE episode TYPE option<bool>;
```

> Because `episode` is `SCHEMAFULL`, undefined fields are silently dropped — the
> v0.8.68 staged-generation domain fields needed this migration to actually
> persist (caught by a live smoke test).

---

## 4. Tables summary

| Table | Kind | Purpose |
|-------|------|---------|
| `notebook` | SCHEMAFULL | Research project container |
| `source` | SCHEMAFULL | Content item (file/URL/text); `asset`, `title`, `topics`, `full_text` |
| `source_embedding` | SCHEMAFULL | Chunked vectors for a source (`order`, `content`, `embedding`) |
| `source_insight` | SCHEMAFULL | Transformation outputs (`insight_type`, `content`, `embedding`) |
| `note` | SCHEMAFULL | Standalone/linked notes (`title`, `summary`, `content`, `note_type`, `embedding`) |
| `chat_session` | SCHEMALESS | Conversation container (`model_override`, `disabled_mcp_servers`) |
| `model` | SCHEMALESS | Registered AI model (`name`, `provider`, `type`, `credential`) |
| `credential` | SCHEMAFULL | Encrypted provider credentials |
| `transformation` | SCHEMAFULL | Reusable transformation prompts |
| `episode_profile` | SCHEMAFULL | Podcast generation config |
| `speaker_profile` | SCHEMAFULL | Podcast voices/personalities |
| `episode` | SCHEMAFULL | Generated podcast episode + job link |
| `memory_fact` / `memory_preference` / `memory_episode` | SCHEMAFULL | Closed-loop memory (HNSW 768) |
| `gmail_integration` | SCHEMAFULL | Gmail digest OAuth + prefs |
| `mcp_server` | SCHEMAFULL | MCP tool-server registry |
| `podcast_config` | SCHEMALESS | Legacy podcast config |
| `_sbl_migrations` | (auto) | Migration version tracking |
| `open_notebook:default_models` / `:default_prompts` / `:provider_configs` | singleton records | Global config |

### Edge (relation) tables

| Edge | Direction | `in` | `out` | Meaning |
|------|-----------|------|-------|---------|
| `reference` | `FROM source TO notebook` | source | notebook | A source belongs to a notebook |
| `artifact` | `FROM note TO notebook` | note | notebook | A note belongs to a notebook |
| `refers_to` | `FROM chat_session TO notebook\|source` | chat_session | notebook/source | A chat is scoped to a notebook or source |

---

## 5. Search functions

Two user-defined SurrealQL functions provide hybrid search. Final form (after
migration 21):

- **`fn::text_search($query_text, $match_count, $sources, $show_notes)`** — BM25
  full-text search across `source.title`, `source.full_text`, `source_embedding.content`,
  `source_insight.content`, `note.title`, `note.content`. Uses `@1@` match
  operator + `search::highlight` + `search::score(1)`; unions all result sets and
  returns `id, title, content, parent_id, relevance` ordered by relevance.

- **`fn::vector_search($query, $match_count, $sources, $show_notes, $min_similarity)`**
  — semantic search using the HNSW KNN operator and cosine similarity:

  ```sql
  SELECT source.id as id, source.title as title, content, source.id as parent_id,
         vector::similarity::cosine(embedding, $query) as similarity
  FROM source_embedding
  WHERE embedding <|100|> $query
    AND embedding != none AND array::len(embedding)=array::len($query)
    AND vector::similarity::cosine(embedding, $query) >= $min_similarity
  ORDER BY similarity DESC LIMIT $match_count
  ```

Both are called from `open_notebook/domain/notebook.py`:

```python
async def vector_search(keyword, results, source=True, note=True, minimum_score=None):
    if minimum_score is None:
        minimum_score = _vector_min_score()      # env-tunable, default 0.3
    embed = await generate_embedding(keyword)
    return await repo_query(
        "SELECT * FROM fn::vector_search($embed, $results, $source, $note, $minimum_score);",
        {"embed": embed, "results": results, "source": source, "note": note,
         "minimum_score": minimum_score},
    )
```

---

## 6. Domain models

Domain models are Pydantic v2 classes in `open_notebook/domain/` (+
`open_notebook/podcasts/models.py`, `open_notebook/ai/models.py`), bound to tables
via two base classes in `open_notebook/domain/base.py`.

### Base classes

- **`ObjectModel`** (mutable records). Fields: `id`, `created`, `updated`;
  ClassVars `table_name` and `nullable_fields` (fields allowed to persist as
  `None`). Methods: `save()`, `delete()`, `relate(relationship, target_id)`,
  `get(id)` (polymorphic — resolves subclass from the `table:id` prefix),
  `get_all(order_by, limit, offset)`. `_prepare_save_data()` drops `None` values
  unless the field is in `nullable_fields`.
- **`RecordModel`** (singletons). Fixed `record_id` per subclass, `update()`
  upserts, lazy `_load_from_db()`. Used by `ContentSettings`, `DefaultPrompts`.

```python
class ObjectModel(BaseModel):
    id: Optional[str] = None
    table_name: ClassVar[str] = ""
    nullable_fields: ClassVar[set[str]] = set()
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
```

### `notebook.py`

- **`Notebook`** (`table_name = "notebook"`): `name` (non-empty validated),
  `description`, `archived`. Navigation: `get_sources()` (via `reference` edge),
  `get_notes()` (via `artifact`), `get_chat_sessions()`. `get_delete_preview()`
  returns counts; `delete(delete_exclusive_sources)` always deletes notes,
  optionally deletes exclusive sources, always unlinks all sources.
- **`Source`** (`table_name = "source"`): `asset` (file/URL ref via `Asset`),
  `title`, `topics`, `full_text`, `command`. `vectorize()` submits an async embed
  job (fire-and-forget, returns command_id); `add_insight()` submits
  `create_insight_command`; `get_status()` / `get_processing_progress()` poll via
  `surreal_commands`; `get_context()` returns an LLM-context summary.
- **`Note`** (`table_name = "note"`): `title`, `summary`, `content`, `note_type`,
  `embedding`. `save()` auto-submits an `embed_note` command;
  `add_to_notebook()` links via `artifact`.
- **`SourceEmbedding`** (`source_embedding`), **`SourceInsight`** (`source_insight`),
  **`Asset`** (helper BaseModel).
- **`ChatSession`** (`table_name = "chat_session"`): optional `model_override`;
  `relate_to_notebook()` / `relate_to_source()` create the `refers_to` edge.
- Module functions `text_search(...)` and `vector_search(...)` (see §5).

### `credential.py` — `Credential`

`table_name = "credential"`. Stores per-provider auth. `api_key` is a Pydantic
`SecretStr` (masked in logs). Custom serialization:

- `_prepare_save_data()` **encrypts** `api_key` with `encrypt_value()` before
  storage.
- `get()` / `get_all()` / `_from_db_row()` **decrypt** on read; `get_all()` has
  per-row error handling (sets `decryption_error="Failed to decrypt API key…"`
  and `api_key="UNDECRYPTABLE"` when the encryption key changed).
- `to_esperanto_config()` builds the config dict passed to Esperanto's
  `AIFactory.create_*()` (api_key, base_url/endpoint, api_version, per-modality
  endpoints, project/location/credentials_path; Azure maps `base_url`→`endpoint`).
- `get_by_provider(provider)`, `get_linked_models()`.

```python
def _prepare_save_data(self) -> dict[str, Any]:
    data = {}
    for key, value in self.model_dump().items():
        if key == "decryption_error":
            continue
        if key == "api_key":
            data["api_key"] = encrypt_value(self.api_key.get_secret_value()) if self.api_key else None
        elif value is not None or key in self.__class__.nullable_fields:
            data[key] = value
    return data
```

### `ai/models.py` — `Model`

`table_name = "model"`, `nullable_fields = {"credential"}`. Fields: `name`,
`provider`, `type` (e.g. `language`/`embedding`/`speech_to_text`/`text_to_speech`),
`credential` (record reference). `get_models_by_type()`, `get_by_credential()`,
`get_credential_obj()`. Its `delete()` proactively clears the seven
`default_models` singleton reference fields (`default_chat_model`,
`default_transformation_model`, `large_context_model`, `default_text_to_speech_model`,
`default_speech_to_text_model`, `default_embedding_model`, `default_tools_model`,
`auto_route_cloud`) and warns about referencing podcast profiles. Esperanto
`ModelType = LanguageModel | EmbeddingModel | SpeechToTextModel | TextToSpeechModel`.

### `podcasts/models.py`

- **`EpisodeProfile`** (`episode_profile`): `name`, `description`,
  `speaker_config` (name reference), `default_briefing`, `num_segments`
  (validated 3–20), `language` (BCP 47), new model refs `outline_llm` /
  `transcript_llm` (legacy `outline_provider`/`outline_model`/`transcript_provider`/
  `transcript_model` kept nullable). `resolve_outline_config()` /
  `resolve_transcript_config()` → `(provider, model_name, config_dict)`.
- **`SpeakerProfile`** (`speaker_profile`): `name`, `description`, `voice_model`
  (model ref; legacy `tts_provider`/`tts_model` nullable), `speakers` (1–4 dicts,
  each requiring `name`, `voice_id`, `backstory`, `personality`; per-speaker
  `voice_model` override). `resolve_tts_config()`.
- **`PodcastEpisode`** (`episode`): `name`, `episode_profile`/`speaker_profile`
  (dict snapshots), `briefing`, `briefing_suffix`, `content`, `audio_file`,
  `transcript`, `outline`, `command` (surreal_commands link), `generation_stage`
  (one of `GENERATION_STAGES`), `cancel_requested`. `nullable_fields =
  {"generation_stage"}` so a `None` stage on success reaches the DB.
  `get_job_status()` / `get_job_detail()` poll the command.

  ```python
  STAGE_OUTLINE = "generating_outline"
  STAGE_TRANSCRIPT = "generating_transcript"
  STAGE_AUDIO = "generating_audio"
  STAGE_COMBINE = "combining_audio"
  STAGE_AWAITING_REVIEW = "awaiting_review"
  STAGE_CANCELLED = "cancelled"
  ```

`_resolve_model_config(model_id)` (module helper) loads a `Model`, resolves its
`Credential` to an Esperanto config, and falls back to `provision_provider_keys()`
when no credential is linked.

### `content_settings.py` / `transformation.py`

- **`ContentSettings`** (`RecordModel` singleton): processing engines, embedding
  strategy, file-deletion policy, YouTube languages.
- **`Transformation`** (`ObjectModel`): reusable transformation; **`DefaultPrompts`**
  (`RecordModel`) holds the transformation-instructions prompt.

---

## 7. Repository layer

`open_notebook/database/repository.py` is the only SurrealQL gateway. Connection
helpers: `get_database_url()` (`SURREAL_URL` or `SURREAL_ADDRESS`+`SURREAL_PORT`),
`get_database_password()` (`SURREAL_PASSWORD` → legacy `SURREAL_PASS`),
`db_connection()` (async context manager: sign-in → select ns/db → yield → close).

CRUD/relation primitives:

| Function | Purpose |
|----------|---------|
| `repo_query(query_str, vars)` | Raw SurrealQL with param substitution → list of dicts |
| `repo_create(table, data)` | Insert; auto-adds `created`/`updated`; strips inbound `id` |
| `repo_insert(table, data_list, ignore_duplicates)` | Bulk insert |
| `repo_upsert(table, id, data, add_timestamp)` | MERGE create-or-update |
| `repo_update(table, id, data)` | Update by id; auto-`updated`; parses ISO dates |
| `repo_delete(record_id)` | Delete by RecordID |
| `repo_relate(source, relationship, target, data)` | Create a graph edge |
| `parse_record_ids(obj)` | Recursively stringify `RecordID`s |
| `ensure_record_id(value)` | Coerce string/`RecordID` → `RecordID` |

Notes: no connection pooling (one connection per call, HTTP-request-scoped);
`RuntimeError` transaction conflicts are logged at DEBUG (retriable, avoids log
spam under concurrency).

---

## 8. Recurring schema gotchas (from CLAUDE.md)

- **Edge direction** — `in`/`out` is easy to invert for `reference` / `artifact` /
  `refers_to`. Always check the `FROM … TO …` clause.
- **SCHEMAFULL drops undefined fields** — adding a domain field requires a
  migration for `SCHEMAFULL` tables (`episode`, `source`, `note`, …) or the value
  silently vanishes.
- **Delete cascades** — only `source` has a DB-level `DEFINE EVENT` cascade
  (→ embeddings + insights). Notebook/profile cascades are handled in Python
  (`Notebook.delete`, `Model.delete`); profiles do **not** cascade to episodes.
- **Embedding dimension** — all HNSW indexes are `DIMENSION 768`; the embedding
  model must output 768-dim vectors (`nomic-embed-text-v1.5`). `fn::vector_search`
  guards against length mismatch.
- **Migration contiguity** — never leave a gap in `1..N.surrealql`; the manager
  refuses to run a partial set.

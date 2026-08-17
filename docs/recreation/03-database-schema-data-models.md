# 03 — Database Schema & Data Models

> SurrealDB 2.x. **92 forward migrations** with paired `_down` files.
> ~75 tables. Namespace/database default to `open_notebook` — a deliberately
> retained persisted-identity literal (see doc 14 §Rebrand Audit).

---

## 1. Why SurrealDB

One engine provides all three shapes the product needs:

| Need | SurrealDB feature |
|---|---|
| Documents (sources, notes) | `SCHEMAFULL` tables with typed fields |
| Graph (notebook ↔ source ↔ note) | Edge tables (`RELATE`), `<-`/`->` traversal |
| Vector search (RAG) | `array<float>` fields + `vector::similarity::cosine` |

The alternative — Postgres + pgvector + a graph layer — needs a server the user must
install. SurrealDB ships as one bundled binary and starts in-process.

## 2. Migration system

`deeper_notebook/database/async_migrate.py`. Numbered `.surrealql` files:

```
deeper_notebook/database/migrations/
  1.surrealql   1_down.surrealql
  ...
  46.surrealql  46_down.surrealql     ← source_visual_* tables
  ...
  92.surrealql  92_down.surrealql
```

Rules that must be preserved:

1. **Every forward migration has a `_down`.** Downgrade is a tested path, not aspiration.
2. **Idempotent DDL.** Every statement uses `IF NOT EXISTS`.
3. **SHA-256 recorded per migration.** Integration proofs assert exact digests, e.g.
   migration 46 up = `d64bdbbf2bcb7d8e56c961b080a03295767c6a64483d772cab311e83f3b38e34`.
4. **Cascade via `DEFINE EVENT`,** not application code — deletes stay consistent even
   for rows the app didn't write.

## 3. Core tables

### `source` — the atom of the system

```sql
DEFINE TABLE IF NOT EXISTS source SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS asset ON TABLE source FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS title ON TABLE source TYPE option<string>;
DEFINE FIELD IF NOT EXISTS topics ON TABLE source TYPE option<array<string>>;
DEFINE FIELD IF NOT EXISTS full_text ON TABLE source TYPE option<string>;
DEFINE FIELD IF NOT EXISTS created ON source
  DEFAULT time::now() VALUE $before OR time::now();   -- created is immutable
DEFINE FIELD IF NOT EXISTS updated ON source
  DEFAULT time::now() VALUE time::now();              -- updated always bumps
```

The `$before OR time::now()` idiom is the canonical immutable-created pattern; copy it
for any new table.

### `source_embedding` / `source_insight` — chunks and derived content

```sql
DEFINE TABLE IF NOT EXISTS source_embedding SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS source    ON TABLE source_embedding TYPE record<source>;
DEFINE FIELD IF NOT EXISTS order     ON TABLE source_embedding TYPE int;
DEFINE FIELD IF NOT EXISTS content   ON TABLE source_embedding TYPE string;
DEFINE FIELD IF NOT EXISTS embedding ON TABLE source_embedding TYPE array<float>;
```

### Cascade delete as a database event

```sql
DEFINE EVENT IF NOT EXISTS source_delete ON TABLE source WHEN ($after == NONE) THEN {
    delete source_embedding where source == $before.id;
    delete source_insight   where source == $before.id;
};
```

## 4. Graph edges

| Edge | From → To | Meaning |
|---|---|---|
| `reference` | notebook → source | Source belongs to notebook |
| `artifact` | notebook → note | Note belongs to notebook |
| `refers_to` | note → source | Note cites source |
| `note_link` | note → note | Wiki-style `[[link]]` |

Counts come from traversal, not joins:

```sql
SELECT *,
  count(<-reference.in) AS source_count,
  count(<-artifact.in)  AS note_count
FROM notebook
WHERE archived = $archived
ORDER BY updated desc
```

## 5. Table families (~75 total)

| Family | Tables |
|---|---|
| Core | `source`, `source_embedding`, `source_insight`, `note`, `notebook`, `chat_session` |
| Edges | `reference`, `artifact`, `refers_to`, `note_link`, `note_block` |
| Knowledge engine | `knowledge_engine_{document,block,relation,space,view,task,asset,identity_map,projection_receipt,source_revision,backfill_checkpoint}` |
| Navigation | `knowledge_bookmark`, `knowledge_bookmark_folder`, `knowledge_navigation_operation_receipt`, `named_knowledge_workspace` |
| Vault | `vault_file`, `vault_mount`, `vault_revision`, `vault_sync_receipt`, `vault_trust_record` |
| Overlay | `overlay_note`, `overlay_space`, `overlay_revision`, `overlay_mutation_receipt` |
| Study | `study_{plan,card,unit,review,progress,syllabus,plan_card,plan_source,plan_memory,plan_artifact}` |
| Study/Anki | `study_anki_{card_compat,export,import,job}` |
| Study/assistant | `study_assistant_session`, `study_assistant_handoff` |
| Podcasts | `podcast_config`, `episode`, `episode_profile`, `speaker_profile` |
| Studio | `studio_workflow_run`, `studio_artifact` |
| Capture | `capture_inbox_item`, `capture_inbox_root`, `capture_fingerprint` |
| Memory | `memory_fact`, `memory_preference`, `memory_episode` |
| Source visuals | `source_visual_cache`, `source_visual_claim`, `source_visual_operation` |
| Analysis | `analysis_run`, `analysis_output`, `claim_verdict`, `evaluation_run`, `research_run` |
| Config | `credential`, `transformation`, `mcp_server`, `gmail_integration` |

## 6. Query access layer

Everything goes through `repo_query` (`deeper_notebook/database/repository.py`):

```python
async def repo_query(
    query_str: str,
    vars: Optional[dict[str, Any]] = None,
    *,
    timeout_s: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Execute a SurrealQL query and return the results.
    v0.7.120 — times every query; logs slow ones above
    DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS."""
```

**The rule that keeps this safe:** *identifiers* may be interpolated only after
whitelist validation; *values* always travel as `$`-bound parameters in `vars`.

```python
# api/routers/notebooks.py — allowlist BEFORE interpolation
allowed_fields     = {"name", "created", "updated"}
allowed_directions = {"asc", "desc"}
# ... parts validated, 400 raised otherwise ...
where_clause = ""
params: dict = {}
if archived is not None:
    where_clause = "WHERE archived = $archived"   # value is BOUND
    params["archived"] = archived
query = f"""
    SELECT *, count(<-reference.in) AS source_count
    FROM notebook
    {where_clause}
    ORDER BY {validated_order_by}
"""   # nosec B608 - constants/whitelisted identifiers; values bound
```

Record ids are parsed, never trusted:

```python
# api/command_service.py — v0.8.87 hardening
record_id = ensure_record_id(
    job_id if job_id.startswith("command:") else f"command:{job_id}"
)   # RecordID.parse rejects malformed input before it reaches the query
```

## 7. Vector search

```python
rows = await repo_query(
    "SELECT content, vector::similarity::cosine(embedding, $q) AS score "
    "FROM memory_fact WHERE embedding <|$limit|> $q",
    {"q": q_vec, "limit": _MAX_FACTS},
)
```

Embeddings come from the local nomic-embed-text sidecar by default; dimensionality
follows the configured embedding model. Changing models requires an embedding rebuild —
see `api/routers/embedding_rebuild.py`.

## 8. Domain model layer

`deeper_notebook/domain/base.py` provides an async-active-record base:

```python
class ObjectModel(BaseModel):
    id: Optional[str] = None
    async def save(self) -> None: ...
    @classmethod
    async def get(cls, id: str) -> "ObjectModel": ...
    @classmethod
    async def get_all(cls, order_by: str | None = None,
                      limit: int | None = None,
                      offset: int | None = None) -> list["ObjectModel"]: ...
    async def delete(self) -> bool: ...
```

`order_by` is validated against a per-model field allowlist and raises
`InvalidInputError` on anything else.

Concrete models: `Notebook`, `Source`, `Note`, `ChatSession`, `Credential`,
`Transformation`, `ContentSettings`, `ProviderConfig`, `GmailIntegration`.

## 9. Connection pooling

```
DEEPER_NOTEBOOK_DB_POOL_SIZE=4        # 1–32
DEEPER_NOTEBOOK_DB_POOL_DISABLED=     # 1 to disable (debug only)
DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS=    # threshold for slow-query WARN
DEEPER_NOTEBOOK_SURREAL_TCP_TIMEOUT=  # connect timeout
```

## 10. Integration-test protocol

Integration tests mint a **throwaway namespace** `onp_test_<uuid>` on a loopback
instance and tear it down after. They never touch the user's data.

```bash
SURREAL_INTEGRATION=1 uv run pytest -q tests/integration/ -m integration_surreal
```

Proofs assert byte-for-byte preservation of pre-existing rows across migrate down/up.

---

*Continues in [04 — Backend API Specifications](./04-backend-api-specifications.md).*

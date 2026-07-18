# Live Source Ingestion Smoke

Use this opt-in smoke when you need proof beyond fixture tests. It talks to a
running native Open Notebook Plus API and verifies:

1. A text, upload, or link source can be created through the real API.
2. The background worker finishes processing it.
3. The source detail API returns extracted text containing a unique marker.
4. Embedding completed, unless `--skip-embedding` is used for a fresh local
   setup without an embedding model.
5. Optionally, source chat can stream an answer from that source.

Open Notebook Plus should be running natively on the host. Do not use Docker
for this proof.

## Basic Run

```bash
python scripts/live_source_ingestion_smoke.py \
  --base-url http://127.0.0.1:5055
```

The script creates a short text source, waits up to 120 seconds, prints a JSON
proof summary, and deletes the smoke source afterward.

## Prove Upload And Link Ingestion Too

```bash
python scripts/live_source_ingestion_smoke.py \
  --base-url http://127.0.0.1:5055 \
  --source-kind all
```

`--source-kind all` creates one text source, one generated `.txt` upload, and
one link source backed by a temporary local HTTP page. Use `--source-kind upload`
or `--source-kind link` for a narrower run. To point at specific material:

```bash
python scripts/live_source_ingestion_smoke.py \
  --base-url http://127.0.0.1:5055 \
  --source-kind upload \
  --upload-file ~/Desktop/sample-training-guide.pdf

python scripts/live_source_ingestion_smoke.py \
  --base-url http://127.0.0.1:5055 \
  --source-kind link \
  --link-url https://example.com/training-source
```

If the native app does not yet have an embedding model configured, use:

```bash
python scripts/live_source_ingestion_smoke.py \
  --base-url http://127.0.0.1:5055 \
  --source-kind all \
  --skip-embedding
```

## Keep The Source For Manual Inspection

```bash
python scripts/live_source_ingestion_smoke.py \
  --base-url http://127.0.0.1:5055 \
  --keep-source
```

## Attach To A Notebook

```bash
python scripts/live_source_ingestion_smoke.py \
  --base-url http://127.0.0.1:5055 \
  --notebook-id notebook:your-id
```

## Include Source Chat

Only use this when the running app has a working chat model.

```bash
python scripts/live_source_ingestion_smoke.py \
  --base-url http://127.0.0.1:5055 \
  --chat-question "What marker appears in this source?"
```

## Authenticated Runs

If the native API requires auth, pass a bearer token with:

```bash
ONP_API_TOKEN="..." python scripts/live_source_ingestion_smoke.py
```

Do not commit tokens or command transcripts that include secrets.

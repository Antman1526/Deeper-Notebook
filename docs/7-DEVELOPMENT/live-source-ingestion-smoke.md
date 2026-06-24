# Live Source Ingestion Smoke

Use this opt-in smoke when you need proof beyond fixture tests. It talks to a
running native Open Notebook Plus API and verifies:

1. A source can be created through the real API.
2. The background worker finishes processing it.
3. The source detail API returns extracted text containing a unique marker.
4. Embedding completed.
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

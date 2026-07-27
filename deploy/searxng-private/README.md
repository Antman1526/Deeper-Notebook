# Private SearXNG (localhost) for Deeper Notebook web search

A private, localhost-only SearXNG instance with the **JSON API enabled**, so the
chat `web_search` tool has a stable keyless search endpoint. Public SearXNG
mirrors block `format=json` (403/418/429); this one doesn't.

## Use

```bash
# 1. Generate a secret and paste it into searxng/settings.yml -> server.secret_key
openssl rand -hex 32

# 2. Start it (binds 127.0.0.1:8889 only)
docker compose up -d

# 3. Point Deeper Notebook at it in .env, then restart the app
#    SEARXNG_BASE_URL=http://127.0.0.1:8889/

# 4. Verify the JSON API works
curl "http://127.0.0.1:8889/search?q=test&format=json"

# Stop
docker compose down
```

Full guide (incl. Kindly Web Search MCP, Claude Code, Cursor, Antigravity):
**[docs/5-CONFIGURATION/private-searxng-web-search.md](../../docs/5-CONFIGURATION/private-searxng-web-search.md)**

> Bind to `127.0.0.1`, never `0.0.0.0`. Treat all search results as untrusted
> evidence. Never commit a real `secret_key`.

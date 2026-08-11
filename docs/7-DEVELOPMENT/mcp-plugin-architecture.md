# MCP plugin architecture

Deeper Notebook's plugin-extension surface is the registered MCP server
catalog. A plugin is an independently started process that exposes a
streamable-HTTP MCP endpoint. Deeper Notebook is the authenticated registry,
discovery client, and isolation boundary; it is not a generic Python plugin
loader.

This page is the architecture reference for maintainers and plugin authors.
For the user-facing setup guide, see [MCP integration](../5-CONFIGURATION/mcp-integration.md).

## Components and authority

```text
operator starts plugin process
          |
          v
streamable HTTP MCP endpoint  <-- one process boundary -->  Deeper Notebook
                                                          |
                              mcp_server registry + MCPClient + chat tool loop
```

- The `mcp_server` table is the catalog. A row contains `name`, `url`,
  `enabled`, and (when present) `priority`/timestamps.
- The Settings UI and authenticated `/api/mcp` routes own registration and
  lifecycle intent. The chat graph reads only enabled rows.
- `MCPClient` opens a fresh streamable-HTTP session for discovery or a tool
  call. Tool names, schemas, content blocks, text, binary data, timeouts, and
  caches are bounded before they reach the chat model.
- The plugin process owns its code, dependencies, data, and shutdown. A
  plugin is never imported or executed merely because a file exists in a
  directory. Do not add an arbitrary in-process loader.

## Registration and lifecycle

Use Settings → MCP Servers, or the authenticated API, to manage rows:

| Operation | Route | Effect |
| --- | --- | --- |
| List | `GET /api/mcp` | Show registered rows. |
| Register | `POST /api/mcp` | Validate the URL and create a disabled/ enabled row. |
| Enable/disable or reorder | `PATCH /api/mcp/{server_id}` | Change `enabled` and/or `priority`. |
| Probe | `POST /api/mcp/{server_id}/test` | Run `list_tools` and return `{ok, tools}` or `{ok, error}`. |
| Remove | `DELETE /api/mcp/{server_id}` | Delete the catalog row; it does not stop an external process. |

Registration validates the URL before storing it and the probe validates it
again before making an outbound request. Keep local plugins on loopback unless
you have explicitly secured and network-isolated them. The optional
`DEEPER_NOTEBOOK_MCP_AUTH_HEADER` supplies one outbound header for a protected
endpoint; never commit that value.

The operator owns process lifecycle: start the plugin before enabling its row,
keep it supervised by the local service manager or terminal, and stop it after
disabling/removing the row. Deeper Notebook does not spawn, restart, or kill
plugin processes. Probe status is on-demand; the current catalog does not
persist health, latency, or last-error state.

During chat, enabled rows are ordered by priority. Discovery is cached for a
short TTL with a finite cache; an operator can disable a server for one
conversation with `disabled_mcp_servers` without changing the catalog. A new
tool surface is therefore observed after the discovery TTL or an explicit
cache-clearing/restart path.

## Failure isolation and budgets

MCP is optional. A registry/database error, malformed row, failed server,
malformed tool, invalid schema, or invalid result block degrades to no tools
from that source. Other registered servers and native tools continue, and
startup does not depend on any plugin being reachable.

The client applies finite limits before materialization or model binding:

- server and tool counts, names, descriptions, schema depth/items/strings;
- content-block count, per-block and result-wide text/binary payloads, URIs,
  MIME types, and safe representations;
- RPC, tool, and model timeouts plus agent iteration caps;
- discovery cache entries and TTL.

Tool output is untrusted data. The chat loop fences it before model use and
does not treat plugin text as instructions. A plugin must not be granted
database credentials or filesystem access it does not need; process-level
isolation remains the primary trust boundary.

## Minimal local example

The repository includes
[`examples/mcp_local_streamable_http.py`](../../examples/mcp_local_streamable_http.py),
a two-tool FastMCP process bound to `127.0.0.1:8765/mcp`. The `mcp` package is
already a project dependency; this example does not add a new dependency.

Start it in one terminal:

```bash
uv run python examples/mcp_local_streamable_http.py
```

In another terminal, register it through Settings → MCP Servers with:

```text
Name: Local example
URL:  http://127.0.0.1:8765/mcp
```

Use **Test**, leave the row enabled, and start a chat. The discovered tools
appear with an `mcp_` prefix. Stop the example with `Ctrl-C`, disable/remove
the row, or restart it before testing again. Do not bind this example to
`0.0.0.0` or expose it through a public proxy without adding authentication
and an explicit threat review.

Plugin authors should keep the endpoint contract small and typed, return
finite text/structured values, document startup and shutdown, and provide a
health/probe story that is safe to call repeatedly. The plugin remains an
external process; registration is the explicit approval step.

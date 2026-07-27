# Local-model tool-calling compatibility

*Deeper Notebook v0.8.10+*

The v0.8.0 Phase 2 MCP integration relies on the local chat model
emitting OpenAI-style `tool_calls` when the user's question needs
information from an MCP server (web search, document fetch, gbrain
knowledge graph, etc.). **Not every GGUF in your model folder
supports this.**

When a non-tool-calling model is selected:

- The chat still works for plain conversation.
- The MCP server stays registered and reachable.
- But the model **never emits `tool_calls`** even when the system
  prompt tells it to — because it wasn't fine-tuned to. The chat
  graph's in-node tool loop (v0.8.9) never enters; `[mcp:N]`
  markers may appear (hallucinated) but no actual MCP call fires;
  citation pill popovers stay on the v0.8.10 placeholder.

There is **no runtime error** in this case. The degradation is
silent. This page documents which of the GGUFs shipped by the
default `download_models.sh` script support tool-calling so you
can pick the right one for MCP-backed chats.

---

## Tool-calling support matrix

Tested against the models listed in
`~/Desktop/OpenNotebook/scripts/download_models.sh`. "Supported"
means the model was fine-tuned to emit OpenAI-format `tool_calls`
in its responses when given the equivalent of `tools=[...]` via
`bind_tools`. "Inconsistent" means the model sometimes emits
tool calls but often hallucinates the schema (wrong arg names,
malformed JSON). "Not supported" means the model has no
tool-calling fine-tune; it will ignore the bound tools.

### ✅ Supported — recommended for MCP chat

| GGUF | Notes |
|------|-------|
| `Hermes-3-Llama-3.1-8B-Q4_K_M.gguf` | Best-supported in this list. Original tool-calling fine-tune from NousResearch; the default `pick_default_model()` already prefers Hermes-3 when present. |
| `Mistral-7B-Instruct-v0.3-Q4_K_M.gguf` | v0.3 added native function calling; emits valid tool_calls reliably. |
| `Qwen2.5-7B-Instruct-Q4_K_M.gguf` | Qwen-2.5 has solid tool-call support via Alibaba's fine-tune. |
| `Qwen2.5-14B-Instruct-Q4_K_M.gguf` | Same support story as 7B, larger model. |
| `Qwen2.5-32B-Instruct-Q4_K_M.gguf` | Same, big enough to need 24GB+ RAM. |
| `Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf` | Tool-calling supported; coder fine-tune adds bias toward code-shaped tool args. |
| `Llama-3.2-3B-Instruct-Q4_K_M.gguf` | Meta's official fine-tune supports tool-calling per the v3.2 model card. |
| `Qwen3.6-27B-Q4_K_M.gguf` | Qwen 3.x line has improved tool-calling. |
| `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` | MoE variant; same support, faster decode at the same parameter count. |
| `DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M.gguf` | DeepSeek-V2 added function calling; works but slightly fewer args supported per call. |
| `DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf` | Inherits Qwen-2.5's tool-call support through the R1 distillation. |

### ⚠️ Inconsistent — works sometimes, fails silently

| GGUF | Failure mode |
|------|--------------|
| `Llama-3.2-1B-Instruct-Q4_K_M.gguf` | Too small for reliable tool-call format; emits calls but ~40% have wrong arg names. |
| `Phi-3.5-mini-instruct-Q4_K_M.gguf` | Microsoft's tool-calling support is partial — works for single-arg tools, struggles with `{name, args}` shape. |
| `SmolLM2-1.7B-Instruct-Q4_K_M.gguf` | Same family limitation as Llama-3.2-1B. |

### ❌ Not supported — MCP will silently no-op

| GGUF | Reason |
|------|--------|
| `gemma-2-2b-it-Q4_K_M.gguf` | Gemma 2 instruct does not include tool-calling in its fine-tune. |
| `gemma-2-9b-it-Q4_K_M.gguf` | Same — Google never shipped a tool-calling Gemma variant. |
| `Yi-1.5-9B-Chat-Q4_K_M.gguf` | 01.AI's Yi 1.5 chat fine-tune has no tool-call support. |
| `codellama-13b-instruct.Q4_K_M.gguf` | TheBloke's CodeLlama-13B-Instruct predates the tool-calling era. |

---

## How to pick the right model

If you have **MCP servers registered** and want them used:

1. Open **Settings → Models** and confirm `default_chat_model`
   points at one of the ✅ Supported models above.
2. Optionally set `DEEPER_NOTEBOOK_LOCAL_CHAT_MODEL_ID` in
   `~/.deeper-notebook/launcher.env` (via **Settings →
   Launcher Preferences**, v0.8.6 Item D) to force the smart
   router (v0.8.0 Phase 3) onto a specific supported model.
3. Verify by chatting "What's the top headline on Hacker News
   right now?" — the chat should call your MCP server's search
   tool and a citation pill should appear in the response. The
   pill popover should show the real query + result text (per
   v0.8.1 Item 3 / v0.8.9 / v0.8.10).

If you have **no MCP servers** registered, model choice doesn't
affect this; pick whatever fits your RAM budget.

---

## How the matrix was determined

The matrix above is a best-effort summary of:

- The model card on Hugging Face (search "tool calling" /
  "function calling" sections).
- Empirical smoke tests with `bind_tools([Tool(name="echo",
  description="echo back", coroutine=async lambda s: s)])` and
  a turn like "Use the echo tool to say hi."
- Existing reports from the llama-cpp-python community.

**Corrections welcome.** Open an issue or PR with model name,
GGUF source, llama-cpp-python version, and the test prompt you
used. We'll update this page.

---

## Why some local models don't support tool-calling

Tool-calling is a behaviour the base LLM learns during
instruction-tuning — the model has to be shown enough examples of
"function-call JSON output" during training to know when to emit
it instead of plain text. Older instruct models (Gemma 2, Yi 1.5,
CodeLlama 13B) were fine-tuned before tool-calling became a
common requirement and don't have it baked in.

The MCP protocol itself works fine with any model that emits
valid OpenAI-format tool calls. The chat graph (`open_notebook/
graphs/chat.py:call_model_with_messages`) doesn't care which
specific model produced the call — it iterates whatever
`ai_message.tool_calls` contains. So if a new fine-tune of an
unsupported family adds tool-calling, just drop the GGUF in your
models folder and switch your default — no code change needed.

---

## See also

- [Integrating gbrain as an MCP source](../3-USER-GUIDE/integrating-gbrain-mcp.md)
- [Citations](../3-USER-GUIDE/citations.md)
- [`desktop/CHANGELOG.md`](../../desktop/CHANGELOG.md) — search for
  `v0.8.9` and `v0.8.10` for the chat-graph tool-loop story.

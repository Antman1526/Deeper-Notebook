"""Hermes 3 system prompts + tool definitions for the memory writer agent.

Hermes 3 emits `<tool_call>` JSON blocks when prompted with explicit tool
definitions. We parse those blocks to extract structured memory writes.
"""

from __future__ import annotations

# Tool definitions are inlined in the system prompt because Hermes 3 follows
# its training-time tool-calling format reliably when tools appear up front.
EXTRACT_TURN_SYSTEM_PROMPT = """You are a memory extractor.

From the conversation turn provided, identify EXPLICIT facts about the user
or their workflow that should be remembered for future conversations. Only
extract what was explicitly stated by the user. Never infer unstated
preferences. If the turn contains no explicit facts, emit no tool calls.

Available tools (emit `<tool_call>` blocks):

remember_preference:
  text: the preference (e.g. "Prefers bullet points over paragraphs")
  scope: "user" or "notebook"
  confidence: 0.0 to 1.0

remember_fact:
  text: the fact (e.g. "Working on a dissertation about RAG")
  scope: "user" or "notebook"
  confidence: 0.0 to 1.0

Emit zero, one, or several tool calls — each as a `<tool_call>{...}</tool_call>`
block. Do NOT emit anything else after the tool calls."""


SUMMARIZE_SESSION_SYSTEM_PROMPT = """You are a chat session summarizer.

Given a complete chat transcript, emit a single `remember_episode` tool call
capturing what happened in the session. Be specific about topics discussed and
any decisions / next steps the user articulated.

remember_episode:
  summary: 1-2 sentences capturing the session arc
  topics: list of 2-6 short topic tags
  outcome: one of "next_step_identified", "question_answered", "exploration",
           "decision_made", "no_outcome"
  source_chat_id: the chat session ID (provided in the user message)

Emit exactly one `<tool_call>{...}</tool_call>` block with the remember_episode call."""


def render_extract_user(user_text: str, assistant_text: str) -> str:
    return f"USER TURN: {user_text}\n\nASSISTANT TURN: {assistant_text}"


def render_extract_user_batch(turns: list[tuple[str, str]]) -> str:
    """v0.8.54 — render N (user, assistant) turns as one transcript for the
    batched extractor (Phase 5.1b). Reuses render_extract_user's per-turn
    shape so the same EXTRACT_TURN_SYSTEM_PROMPT applies unchanged; the model
    extracts explicit facts across all the turns in a single LLM call."""
    return "\n\n".join(render_extract_user(u, a) for (u, a) in turns)


def render_summarize_user(chat_session_id: str, transcript: str) -> str:
    return f"CHAT SESSION ID: {chat_session_id}\n\nTRANSCRIPT:\n{transcript}"

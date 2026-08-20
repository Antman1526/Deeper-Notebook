"""Phase 5.3a — Agent-loop state machine (pure core).

Weak local models are prone to two failure modes in multi-step / tool work:
they claim "done" while work remains, or they loop without making progress.
This module gives the agent an explicit lifecycle and enforces two guarantees,
as a dependency-free, fully-unit-testable state machine:

      TODO ──▶ WORKING ──▶ COMPLETE        (terminal)
                │  ▲
                ▼  │
              CLARIFY                       (needs user input; resumes WORKING)
                │
                ▼
              FAILED                        (terminal, unrecoverable)

Guarantees:
  1. **Anti-hallucinated-done.** A model that declares COMPLETE while any
     declared todo item is still open is kept WORKING — "complete" is only
     honored when every todo is satisfied.
  2. **Backstop.** A max-steps ceiling forces termination so a model that
     never declares COMPLETE (or keeps looping) can't run forever.

This is the CORE (5.3a): transitions + a tolerant parser for the model's
declared state + completion validation + a pure step driver. Wiring it into
the `ask` graph / chat tool loop behind `DEEPER_NOTEBOOK_AGENT_FSM` is 5.3b/c — see
`docs/7-DEVELOPMENT/phase-5-advanced-memory.md`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class AgentState(str, Enum):
    TODO = "todo"
    WORKING = "working"
    CLARIFY = "clarify"
    COMPLETE = "complete"
    FAILED = "failed"


_TERMINAL = frozenset({AgentState.COMPLETE, AgentState.FAILED})

# Allowed transitions (from → set of reachable states).
_TRANSITIONS: dict[AgentState, frozenset] = {
    AgentState.TODO: frozenset(
        {AgentState.WORKING, AgentState.CLARIFY, AgentState.FAILED}
    ),
    AgentState.WORKING: frozenset(
        {
            AgentState.WORKING,
            AgentState.CLARIFY,
            AgentState.COMPLETE,
            AgentState.FAILED,
        }
    ),
    AgentState.CLARIFY: frozenset({AgentState.WORKING, AgentState.FAILED}),
    AgentState.COMPLETE: frozenset(),
    AgentState.FAILED: frozenset(),
}


def is_terminal(state: AgentState) -> bool:
    return state in _TERMINAL


def can_transition(frm: AgentState, to: AgentState) -> bool:
    return to in _TRANSITIONS.get(frm, frozenset())


# Parse a model-declared state from free text. Accept either a
# `<state>working</state>` tag or a `STATE: working` line. Tolerant of
# case/whitespace; the LAST declaration wins (the model's final word).
_STATE_TAG = re.compile(r"<\s*state\s*>\s*([A-Za-z_]+)\s*<\s*/\s*state\s*>", re.I)
_STATE_LINE = re.compile(r"(?im)^\s*state\s*[:=]\s*([A-Za-z_]+)\s*$")


def parse_state(text: str) -> AgentState | None:
    """Extract a declared AgentState from model output, or None if absent /
    unrecognized. Prefers the tag form; falls back to a STATE: line."""
    if not text:
        return None
    matches = list(_STATE_TAG.finditer(text)) or list(_STATE_LINE.finditer(text))
    if not matches:
        return None
    raw = matches[-1].group(1).strip().lower()
    try:
        return AgentState(raw)
    except ValueError:
        return None


@dataclass
class TodoItem:
    text: str
    done: bool = False


def completion_satisfied(todos: list[TodoItem]) -> bool:
    """True when every todo is done. An EMPTY list is satisfied (nothing
    outstanding); callers that want to forbid completing with no plan should
    validate the plan separately before trusting this."""
    return all(t.done for t in todos)


@dataclass
class AgentLoop:
    """Pure driver for the FSM with a step backstop. No I/O — feed it the
    model's declared state each step and it returns the enforced next state."""

    max_steps: int = 8
    state: AgentState = AgentState.TODO
    steps: int = 0

    def advance(
        self,
        declared: AgentState | None,
        todos: list[TodoItem] | None = None,
    ) -> AgentState:
        """Advance one step given the model's `declared` next state.

        Rules, in order:
          * Terminal state → stay (idempotent).
          * Increment the step counter; at/over `max_steps`, force terminate
            (COMPLETE if todos satisfied else FAILED) — the backstop.
          * None / unparseable declaration → default to WORKING (keep going)
            rather than trusting a missing/garbled claim.
          * COMPLETE is downgraded to WORKING when todos are not all done
            (anti-hallucinated-done).
          * An illegal declared transition → WORKING if legal, else stay.
        """
        if is_terminal(self.state):
            return self.state
        self.steps += 1
        todos = todos or []

        # Backstop: never run past the ceiling.
        if self.steps >= self.max_steps:
            self.state = (
                AgentState.COMPLETE
                if completion_satisfied(todos)
                else AgentState.FAILED
            )
            return self.state

        target = declared if declared is not None else AgentState.WORKING

        # Anti-hallucinated-done guard.
        if target == AgentState.COMPLETE and not completion_satisfied(todos):
            target = AgentState.WORKING

        # Enforce legal transitions.
        if not can_transition(self.state, target):
            target = (
                AgentState.WORKING
                if can_transition(self.state, AgentState.WORKING)
                else self.state
            )

        self.state = target
        return self.state

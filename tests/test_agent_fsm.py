"""v0.8.52 — Phase 5.3a: agent-loop state-machine core.

Pure unit tests for transitions, the declared-state parser, completion
validation, and the step driver (anti-hallucinated-done + backstop).
"""

from __future__ import annotations

import pytest

from deeper_notebook.graphs.agent_fsm import (
    AgentLoop,
    AgentState,
    TodoItem,
    can_transition,
    completion_satisfied,
    is_terminal,
    parse_state,
)

# ---------------------------------------------------------------------------
# transitions
# ---------------------------------------------------------------------------


def test_terminal_states():
    assert is_terminal(AgentState.COMPLETE)
    assert is_terminal(AgentState.FAILED)
    assert not is_terminal(AgentState.TODO)
    assert not is_terminal(AgentState.WORKING)
    assert not is_terminal(AgentState.CLARIFY)


@pytest.mark.parametrize(
    "frm,to,ok",
    [
        (AgentState.TODO, AgentState.WORKING, True),
        (AgentState.TODO, AgentState.CLARIFY, True),
        (AgentState.TODO, AgentState.COMPLETE, False),  # can't finish before starting
        (AgentState.WORKING, AgentState.WORKING, True),
        (AgentState.WORKING, AgentState.COMPLETE, True),
        (AgentState.WORKING, AgentState.CLARIFY, True),
        (AgentState.CLARIFY, AgentState.WORKING, True),
        (AgentState.CLARIFY, AgentState.COMPLETE, False),  # must resume work first
        (AgentState.COMPLETE, AgentState.WORKING, False),  # terminal
        (AgentState.FAILED, AgentState.WORKING, False),  # terminal
    ],
)
def test_can_transition(frm, to, ok):
    assert can_transition(frm, to) is ok


# ---------------------------------------------------------------------------
# parse_state
# ---------------------------------------------------------------------------


def test_parse_state_tag_form():
    assert parse_state("blah <state>working</state> blah") == AgentState.WORKING
    assert parse_state("<STATE>Complete</STATE>") == AgentState.COMPLETE


def test_parse_state_line_form():
    assert parse_state("reasoning...\nSTATE: clarify\n") == AgentState.CLARIFY
    assert parse_state("state = failed") == AgentState.FAILED


def test_parse_state_last_wins():
    txt = "<state>working</state> ... <state>complete</state>"
    assert parse_state(txt) == AgentState.COMPLETE


def test_parse_state_absent_or_invalid():
    assert parse_state("no marker here") is None
    assert parse_state("<state>banana</state>") is None
    assert parse_state("") is None
    assert parse_state(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# completion_satisfied
# ---------------------------------------------------------------------------


def test_completion_empty_is_satisfied():
    assert completion_satisfied([]) is True


def test_completion_all_done():
    assert completion_satisfied([TodoItem("a", True), TodoItem("b", True)]) is True


def test_completion_some_open():
    assert completion_satisfied([TodoItem("a", True), TodoItem("b", False)]) is False


# ---------------------------------------------------------------------------
# AgentLoop.advance
# ---------------------------------------------------------------------------


def test_advance_todo_to_working_by_default():
    loop = AgentLoop(max_steps=8)
    assert loop.advance(declared=None) == AgentState.WORKING
    assert loop.steps == 1


def test_advance_honors_complete_when_todos_done():
    loop = AgentLoop(max_steps=8, state=AgentState.WORKING)
    todos = [TodoItem("a", True)]
    assert loop.advance(AgentState.COMPLETE, todos) == AgentState.COMPLETE


def test_advance_downgrades_complete_when_todos_open():
    """Anti-hallucinated-done: declared COMPLETE with open todos → WORKING."""
    loop = AgentLoop(max_steps=8, state=AgentState.WORKING)
    todos = [TodoItem("a", True), TodoItem("b", False)]
    assert loop.advance(AgentState.COMPLETE, todos) == AgentState.WORKING


def test_advance_backstop_forces_terminal():
    """At max_steps the loop force-terminates regardless of declaration."""
    loop = AgentLoop(max_steps=3, state=AgentState.WORKING)
    # steps 1, 2 keep working; step 3 hits the backstop.
    assert loop.advance(AgentState.WORKING) == AgentState.WORKING
    assert loop.advance(AgentState.WORKING) == AgentState.WORKING
    final = loop.advance(AgentState.WORKING, todos=[])  # empty todos → satisfied
    assert final == AgentState.COMPLETE
    assert is_terminal(loop.state)


def test_advance_backstop_fails_when_todos_open():
    loop = AgentLoop(max_steps=1, state=AgentState.WORKING)
    final = loop.advance(AgentState.WORKING, todos=[TodoItem("a", False)])
    assert final == AgentState.FAILED


def test_advance_terminal_is_idempotent():
    loop = AgentLoop(state=AgentState.COMPLETE)
    assert loop.advance(AgentState.WORKING) == AgentState.COMPLETE
    assert loop.steps == 0  # no work done from a terminal state


def test_advance_illegal_declared_falls_back_to_working():
    loop = AgentLoop(max_steps=8, state=AgentState.TODO)
    # TODO → COMPLETE is illegal; should fall back to WORKING.
    assert loop.advance(AgentState.COMPLETE, todos=[]) == AgentState.WORKING


def test_advance_clarify_round_trip():
    loop = AgentLoop(max_steps=8, state=AgentState.WORKING)
    assert loop.advance(AgentState.CLARIFY) == AgentState.CLARIFY
    # user answered → back to working
    assert loop.advance(AgentState.WORKING) == AgentState.WORKING


def test_advance_failed_is_terminal():
    loop = AgentLoop(max_steps=8, state=AgentState.WORKING)
    assert loop.advance(AgentState.FAILED) == AgentState.FAILED
    assert loop.advance(AgentState.WORKING) == AgentState.FAILED  # stuck terminal

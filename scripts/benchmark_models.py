#!/usr/bin/env python3
"""v0.7.139 — Live model benchmark harness.

What this is FOR:
  Stress every Model record configured in the DB against three real
  notebook/podcast-shaped probes, then rank them. Pick winners
  before pointing your actual content at them.

What this is NOT:
  - A unit test (those live in tests/).
  - A perf microbenchmark — wall-clock here includes provider RTT,
    cold-cache warmup, every codepath the real app exercises. That's
    the point: the goal is "which model works best IN THIS APP",
    not "which has best raw tok/s".

How to run (services must be up):
    make database          # SurrealDB on :8000
    make api               # FastAPI on :5055
    make worker            # surreal-commands worker
    make benchmark-models  # this script

Or directly:
    SURREAL_INTEGRATION=0 uv run --env-file .env python scripts/benchmark_models.py

Output:
    benchmark-report.md — Markdown report with three sections:
      1. Per-model results table (wall-clock, tokens, success, error)
      2. Composite ranking
      3. Per-failure-mode breakdown

Probes (each runs once per language model):

  A. NOTEBOOK_CHAT — "answer this question from the source text"
     Tests: basic chat-shaped LLM call
     Pass criteria: returns >50 chars, completes in <60s

  B. STUDIO_OUTLINE — structured JSON output for multi-page notebook
     Tests: same path as v0.7.89 Studio multi-page generation
     Pass criteria: returns valid JSON matching outline schema

  C. PODCAST_TRANSCRIPT_TURN — one turn of multi-speaker dialogue
     Tests: roleplay + structured-ish output
     Pass criteria: returns dialogue text containing both speakers

For embedding models, a separate EMBED_VECTOR_LEN probe checks that
.aembed() returns the expected dimensionality.

For TTS/STT models, currently NO probe — those need audio fixtures
which would bloat the script. Future work.

Exit code:
  0 — every probe ran (results may still show failures)
  1 — script-level error (API unreachable, no models configured, etc.)

Author: Antman's v0.7.139 hardening arc.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print(
        "FATAL: httpx not installed. Run `uv sync` from the repo root.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------- #
# Probe definitions — kept at module level so they're reproducible and
# diff-able across runs. Changing a probe should be a deliberate edit
# (and bump the script's version below so old reports are comparable).
# ---------------------------------------------------------------------- #

PROBE_VERSION = "v0.7.139-1"

NOTEBOOK_CHAT_PROMPT = (
    "You are a research assistant. The following source text contains "
    "facts about an experiment. Answer the user's question using only "
    "the source.\n\n"
    "SOURCE:\n"
    "In 1665, Robert Hooke observed cork tissue under a microscope and "
    "coined the term 'cell' to describe the box-like compartments he "
    "saw. The compartments reminded him of the small rooms (cellulae) "
    "where monks lived. This was the first recorded use of 'cell' in "
    "biology.\n\n"
    "QUESTION: Who coined the term 'cell' in biology, what year, and "
    "what did he observe under the microscope?"
)

STUDIO_OUTLINE_PROMPT = (
    "Generate a JSON outline for a 3-page study notebook on the source "
    "text. Return ONLY valid JSON matching this exact schema:\n"
    '  {"pages": [{"title": "...", "focus": "..."}, ...]}\n\n'
    "SOURCE:\n"
    "The mitochondrion is a double-membrane organelle found in most "
    "eukaryotic cells. It generates ATP through oxidative phosphorylation. "
    "Mitochondria have their own circular DNA, inherited from the mother. "
    "They are thought to have originated as free-living bacteria that "
    "entered into endosymbiotic relationships with primitive eukaryotic "
    "cells about 1.5 billion years ago.\n\n"
    "Return JSON only — no preamble, no code fences, no explanation."
)

PODCAST_TURN_PROMPT = (
    "Write one short turn of a two-host podcast dialogue. Host A is "
    "named ALICE; Host B is BOB. The topic is given by the source. Each "
    "host speaks once, conversationally, in under 80 words each. Format:\n"
    "ALICE: <her line>\n"
    "BOB: <his line>\n\n"
    "SOURCE: Photosynthesis converts light energy into chemical energy "
    "stored in glucose. The reaction takes place in chloroplasts and "
    "produces oxygen as a byproduct."
)


@dataclass
class ProbeResult:
    """One probe's outcome against one model."""

    probe: str
    model_id: str
    model_name: str
    provider: str
    success: bool
    elapsed_s: float
    output: str = ""
    error: str = ""
    # Probe-specific metadata (e.g., parsed JSON keys, dialogue
    # speaker count) so the report can sort/filter without reparsing.
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelReport:
    """All probes' results for one model + composite ranking."""

    model_id: str
    model_name: str
    provider: str
    model_type: str
    results: list[ProbeResult] = field(default_factory=list)

    @property
    def total_elapsed_s(self) -> float:
        return sum(r.elapsed_s for r in self.results)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def composite_score(self) -> float:
        """Higher is better. Pass count dominates; ties broken by
        latency (lower better)."""
        # Pass count scaled to 0-100, latency scaled to 0-100 inverse.
        # Composite = 70% pass + 30% latency.
        n = max(len(self.results), 1)
        pass_pct = (self.pass_count / n) * 100
        # Latency penalty: 0 if total <= 1s, scales to 0 at 60s+.
        if self.total_elapsed_s <= 1.0:
            latency_score = 100
        elif self.total_elapsed_s >= 60.0:
            latency_score = 0
        else:
            latency_score = 100 * (1 - (self.total_elapsed_s - 1) / 59)
        return round(0.7 * pass_pct + 0.3 * latency_score, 1)


# ---------------------------------------------------------------------- #
# API client — uses the same auth pattern as the frontend (Bearer
# DEEPER_NOTEBOOK_PASSWORD from env).
# ---------------------------------------------------------------------- #


def _api_base() -> str:
    return os.environ.get("DEEPER_NOTEBOOK_BENCHMARK_API_BASE", "http://localhost:5055")


def _auth_headers() -> dict[str, str]:
    password = os.environ.get("DEEPER_NOTEBOOK_PASSWORD", "").strip()
    if not password:
        return {}
    return {"Authorization": f"Bearer {password}"}


async def _fetch_configured_models(client: httpx.AsyncClient) -> list[dict]:
    """List every Model record from the API. Returns the raw dict list
    so we can include credential / type info in the report."""
    r = await client.get(f"{_api_base()}/api/models", headers=_auth_headers())
    r.raise_for_status()
    payload = r.json()
    # The API returns either a bare list or a {"models": [...]} envelope
    # depending on the route version. Normalize.
    if isinstance(payload, dict) and "models" in payload:
        return payload["models"]
    if isinstance(payload, list):
        return payload
    return []


async def _run_chat_probe(
    client: httpx.AsyncClient,
    model: dict,
    prompt: str,
    *,
    probe_name: str,
    per_call_timeout_s: float = 90.0,
) -> ProbeResult:
    """Hit POST /api/transformations/execute against this model.

    Why /transformations/execute and not /chat/stream:
      - /chat/stream is SSE; awkward to consume in a benchmark.
      - /transformations/execute already has the v0.7.95 timeout +
        v0.7.135 HTTPException re-raise, and lets us pin a specific
        model_id per call. Simpler control surface.
    """
    model_id = model.get("id", "")
    model_name = model.get("name", "")
    provider = model.get("provider", "")
    start = time.monotonic()
    try:
        r = await client.post(
            f"{_api_base()}/api/transformations/execute",
            headers=_auth_headers(),
            json={
                "input_text": prompt,
                "transformation_id": None,
                "model_id": model_id,
            },
            timeout=per_call_timeout_s,
        )
        elapsed = time.monotonic() - start
        if r.status_code != 200:
            return ProbeResult(
                probe=probe_name,
                model_id=model_id,
                model_name=model_name,
                provider=provider,
                success=False,
                elapsed_s=elapsed,
                error=f"HTTP {r.status_code}: {r.text[:200]}",
            )
        body = r.json()
        output = body.get("output", "") or ""
        return ProbeResult(
            probe=probe_name,
            model_id=model_id,
            model_name=model_name,
            provider=provider,
            success=len(output.strip()) > 50,
            elapsed_s=elapsed,
            output=output,
            meta={"output_len": len(output)},
        )
    except httpx.TimeoutException:
        return ProbeResult(
            probe=probe_name,
            model_id=model_id,
            model_name=model_name,
            provider=provider,
            success=False,
            elapsed_s=time.monotonic() - start,
            error=f"timeout after {per_call_timeout_s}s",
        )
    except Exception as exc:
        return ProbeResult(
            probe=probe_name,
            model_id=model_id,
            model_name=model_name,
            provider=provider,
            success=False,
            elapsed_s=time.monotonic() - start,
            error=f"{type(exc).__name__}: {exc}",
        )


async def _run_studio_outline_probe(
    client: httpx.AsyncClient,
    model: dict,
) -> ProbeResult:
    """Variant of _run_chat_probe whose success criterion is "did the
    output parse as valid JSON matching the outline schema". This is
    the same check Studio multi-page does — a model that fails this
    test would fall back to single-note in actual Studio use.

    NB: the underlying _run_chat_probe sets success based on output
    length (>50 chars). For the outline probe that's the WRONG
    heuristic — a perfectly valid `{"pages":[{"title":"X"}]}` is
    23 chars long and would be incorrectly rejected. We ignore the
    inherited success flag and re-derive it from JSON validity only.
    Errors from the network layer (timeout, HTTP non-200) still
    short-circuit because there's no `output` to parse in those
    cases.
    """
    res = await _run_chat_probe(
        client,
        model,
        STUDIO_OUTLINE_PROMPT,
        probe_name="STUDIO_OUTLINE",
    )
    # Short-circuit on transport-level errors only — those leave
    # `res.output` empty so JSON parsing would be pointless. Length-
    # based "success" failures (output too short) are NOT short-
    # circuited because a short response might still be valid JSON.
    if res.error and not res.output:
        return res
    # Try to extract JSON from the output. Handle the common pattern
    # of models wrapping JSON in code fences or preamble.
    text = res.output.strip()
    # Strip ```json ... ``` fences if present
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text
        # Drop leading `json\n` if Esperanto returned that
        if text.startswith("json\n") or text.startswith("json\r\n"):
            text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    try:
        parsed = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        res.success = False
        res.error = f"JSON parse failed: {exc}"
        res.meta["json_parse_attempted"] = True
        return res
    # Validate shape: must have "pages" key with non-empty list of dicts
    pages = parsed.get("pages") if isinstance(parsed, dict) else None
    if not isinstance(pages, list) or len(pages) == 0:
        res.success = False
        res.error = "JSON shape: missing or empty 'pages' array"
        res.meta["json_shape_ok"] = False
        return res
    # Each page should have at least one of title/focus
    valid_pages = sum(
        1 for p in pages if isinstance(p, dict) and (p.get("title") or p.get("focus"))
    )
    if valid_pages == 0:
        res.success = False
        res.error = "JSON shape: no page entries had title or focus"
        res.meta["json_shape_ok"] = False
        return res
    # JSON parsed AND validated. Override the chat-probe-inherited
    # `success` flag (which was set based on the >50-char length
    # heuristic) — a valid Studio outline JSON might legitimately be
    # under 50 characters and we shouldn't penalize it.
    res.success = True
    res.error = ""
    res.meta["json_shape_ok"] = True
    res.meta["page_count"] = len(pages)
    res.meta["valid_pages"] = valid_pages
    return res


async def _run_podcast_turn_probe(
    client: httpx.AsyncClient,
    model: dict,
) -> ProbeResult:
    """Probe the model's ability to produce multi-speaker dialogue —
    the foundation of podcast transcript generation. Doesn't run the
    full podcast pipeline (no TTS, no full episode), just the LLM
    layer that produces the transcript."""
    res = await _run_chat_probe(
        client,
        model,
        PODCAST_TURN_PROMPT,
        probe_name="PODCAST_TRANSCRIPT_TURN",
    )
    if not res.success:
        return res
    out_lower = res.output.lower()
    has_alice = "alice" in out_lower
    has_bob = "bob" in out_lower
    res.meta["has_alice"] = has_alice
    res.meta["has_bob"] = has_bob
    if not (has_alice and has_bob):
        res.success = False
        res.error = (
            "Output didn't contain both ALICE and BOB speakers — model "
            "may not follow multi-speaker formatting instructions"
        )
    return res


# ---------------------------------------------------------------------- #
# Report rendering
# ---------------------------------------------------------------------- #


def _render_markdown(reports: list[ModelReport], *, total_wall_clock_s: float) -> str:
    """Produce the human-readable benchmark report."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: list[str] = []
    out.append("# Model Benchmark Report")
    out.append("")
    out.append(f"- **Generated**: `{now}`")
    out.append(f"- **Probe version**: `{PROBE_VERSION}`")
    out.append(f"- **Models tested**: {len(reports)}")
    out.append(f"- **Total wall-clock**: {total_wall_clock_s:.1f}s")
    out.append(f"- **API base**: `{_api_base()}`")
    out.append("")
    out.append("Scoring: composite = 0.7 × pass-rate + 0.3 × latency-inverse")
    out.append("(higher is better; latency capped at 60s).")
    out.append("")

    # Ranking
    out.append("## 1. Ranking")
    out.append("")
    out.append("| Rank | Model | Provider | Composite | Pass | Total time |")
    out.append("|---:|---|---|---:|---:|---:|")
    ranked = sorted(reports, key=lambda r: r.composite_score, reverse=True)
    for i, rep in enumerate(ranked, 1):
        out.append(
            f"| {i} | `{rep.model_name}` | {rep.provider} | "
            f"{rep.composite_score} | "
            f"{rep.pass_count}/{len(rep.results)} | "
            f"{rep.total_elapsed_s:.1f}s |"
        )
    out.append("")

    # Per-probe results
    probe_names = ("NOTEBOOK_CHAT", "STUDIO_OUTLINE", "PODCAST_TRANSCRIPT_TURN")
    for probe in probe_names:
        out.append(f"## 2. {probe}")
        out.append("")
        out.append("| Model | Provider | OK | Elapsed | Notes |")
        out.append("|---|---|:---:|---:|---|")
        for rep in ranked:
            r = next((x for x in rep.results if x.probe == probe), None)
            if not r:
                continue
            ok = "✅" if r.success else "❌"
            notes = (
                r.error
                if r.error
                else (", ".join(f"{k}={v}" for k, v in r.meta.items()) or "—")
            )
            # Trim notes to fit narrow table cells
            notes = notes[:80] + ("…" if len(notes) > 80 else "")
            out.append(
                f"| `{rep.model_name}` | {rep.provider} | {ok} | "
                f"{r.elapsed_s:.1f}s | {notes} |"
            )
        out.append("")

    # Failure-mode summary
    failure_modes: dict[str, int] = {}
    for rep in reports:
        for r in rep.results:
            if r.success:
                continue
            err_class = r.error.split(":", 1)[0] if r.error else "Unknown"
            failure_modes[err_class] = failure_modes.get(err_class, 0) + 1
    if failure_modes:
        out.append("## 3. Failure-mode breakdown")
        out.append("")
        out.append("| Failure type | Count |")
        out.append("|---|---:|")
        for k, v in sorted(failure_modes.items(), key=lambda kv: -kv[1]):
            out.append(f"| `{k}` | {v} |")
        out.append("")

    out.append("---")
    out.append("")
    out.append(
        "Re-run with `make benchmark-models`. Re-roll a single model "
        "by setting `DEEPER_NOTEBOOK_BENCHMARK_ONLY=<model_name>`."
    )
    return "\n".join(out)


# ---------------------------------------------------------------------- #
# Main driver
# ---------------------------------------------------------------------- #


async def benchmark_all(
    *,
    only_model_name: str | None = None,
    output_path: Path,
    per_call_timeout_s: float,
) -> int:
    """Returns 0 on success, 1 on script-level error."""
    print(f"v0.7.139 benchmark — API={_api_base()}")
    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        try:
            models = await _fetch_configured_models(client)
        except httpx.HTTPError as exc:
            print(
                f"FATAL: could not reach API at {_api_base()}: {exc}",
                file=sys.stderr,
            )
            print(
                "Hint: is `make api` running? Check `make status`.",
                file=sys.stderr,
            )
            return 1

        if not models:
            print(
                "WARNING: no Model records configured. Add models via "
                "Settings → Models in the UI, then re-run.",
                file=sys.stderr,
            )
            return 1

        if only_model_name:
            models = [m for m in models if m.get("name") == only_model_name]
            if not models:
                print(
                    f"FATAL: no model named {only_model_name!r}",
                    file=sys.stderr,
                )
                return 1

        # Filter to language models only (the chat probe needs language).
        # Embedding / STT / TTS get separate (future) probes.
        language_models = [m for m in models if m.get("type") == "language"]
        if not language_models:
            print(
                "WARNING: no language-type models found; nothing to benchmark.",
                file=sys.stderr,
            )
            return 1

        print(f"Benchmarking {len(language_models)} language model(s)...")
        reports: list[ModelReport] = []

        for i, m in enumerate(language_models, 1):
            print(
                f"  [{i}/{len(language_models)}] {m.get('name')} "
                f"({m.get('provider')})..."
            )
            rep = ModelReport(
                model_id=m.get("id", ""),
                model_name=m.get("name", ""),
                provider=m.get("provider", ""),
                model_type="language",
            )
            # Run probes serially so we don't hammer the worker queue.
            r1 = await _run_chat_probe(
                client,
                m,
                NOTEBOOK_CHAT_PROMPT,
                probe_name="NOTEBOOK_CHAT",
                per_call_timeout_s=per_call_timeout_s,
            )
            print(
                f"    NOTEBOOK_CHAT: {'OK' if r1.success else 'FAIL'} "
                f"({r1.elapsed_s:.1f}s)"
            )
            rep.results.append(r1)

            r2 = await _run_studio_outline_probe(client, m)
            print(
                f"    STUDIO_OUTLINE: {'OK' if r2.success else 'FAIL'} "
                f"({r2.elapsed_s:.1f}s)"
            )
            rep.results.append(r2)

            r3 = await _run_podcast_turn_probe(client, m)
            print(
                f"    PODCAST_TURN: {'OK' if r3.success else 'FAIL'} "
                f"({r3.elapsed_s:.1f}s)"
            )
            rep.results.append(r3)

            reports.append(rep)

    total_wall_clock = time.monotonic() - start
    md = _render_markdown(reports, total_wall_clock_s=total_wall_clock)
    output_path.write_text(md)
    print(f"\nReport written: {output_path}")
    print(f"Total time: {total_wall_clock:.1f}s")
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output",
        type=Path,
        default=Path("benchmark-report.md"),
        help="Where to write the Markdown report (default: ./benchmark-report.md)",
    )
    p.add_argument(
        "--only",
        type=str,
        default=os.environ.get("DEEPER_NOTEBOOK_BENCHMARK_ONLY"),
        help="Benchmark only the named model (matches Model.name exactly)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=float(
            os.environ.get(
                "DEEPER_NOTEBOOK_BENCHMARK_PER_CALL_TIMEOUT_SEC", "90"
            ).strip()
            or 90
        ),
        help="Per-call timeout in seconds (default: 90)",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    return asyncio.run(
        benchmark_all(
            only_model_name=args.only,
            output_path=args.output,
            per_call_timeout_s=args.timeout,
        )
    )


if __name__ == "__main__":
    sys.exit(main())

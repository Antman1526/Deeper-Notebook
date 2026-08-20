"""Capability registry for known local model families.

DATA, NOT CODE. Editing this file should never require touching the scoring
or assigner logic in capability.py / assigner.py. To add a model:
  1. Append an entry to MODELS keyed by exact model name (case-sensitive)
  2. Fill all 5 capability scores (chat / reasoning / tools / code / speed)
  3. Set `kind` to one of: "chat", "reasoning", "embed", "stt", "tts"

When a model name isn't in MODELS, capability.py falls back to FALLBACK_PATTERNS
(regex → partial scores) so unknown models still get reasonable defaults.

Capability axes (all 0.0–1.0, higher = better):
  chat        — general conversational quality
  reasoning   — multi-step / chain-of-thought depth
  tools       — function-calling accuracy and JSON adherence
  code        — code generation and review
  speed       — tokens/sec (rough; bigger model = lower)
"""

from __future__ import annotations

CAPABILITY_AXES = ("chat", "reasoning", "tools", "code", "speed")
DEFAULT_SCORES = {axis: 0.5 for axis in CAPABILITY_AXES}

# Per-family scoring. Keys are matched as PREFIXES against model names so
# Q4_K_M / Q5_K_M / Q8_0 / Q6 variants of the same model share one entry.
MODELS: dict[str, dict] = {
    # ---- Hermes (tool-calling specialist) ----
    "Hermes-3-Llama-3.1-8B": {
        "kind": "chat",
        "scores": {
            "chat": 0.85,
            "reasoning": 0.60,
            "tools": 0.95,
            "code": 0.50,
            "speed": 0.70,
        },
        "context_len": 131072,
        "ram_gb_q4": 5,
    },
    # ---- Qwen 2.5 line ----
    "Qwen2.5-1.5B-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.60,
            "reasoning": 0.45,
            "tools": 0.55,
            "code": 0.50,
            "speed": 0.95,
        },
        "context_len": 32768,
        "ram_gb_q4": 1,
    },
    "Qwen2.5-3B-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.70,
            "reasoning": 0.55,
            "tools": 0.65,
            "code": 0.60,
            "speed": 0.90,
        },
        "context_len": 32768,
        "ram_gb_q4": 2,
    },
    "Qwen2.5-7B-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.80,
            "reasoning": 0.70,
            "tools": 0.75,
            "code": 0.70,
            "speed": 0.80,
        },
        "context_len": 131072,
        "ram_gb_q4": 5,
    },
    "Qwen2.5-14B-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.85,
            "reasoning": 0.75,
            "tools": 0.80,
            "code": 0.75,
            "speed": 0.65,
        },
        "context_len": 131072,
        "ram_gb_q4": 9,
    },
    "Qwen2.5-32B-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.90,
            "reasoning": 0.85,
            "tools": 0.85,
            "code": 0.85,
            "speed": 0.45,
        },
        "context_len": 131072,
        "ram_gb_q4": 20,
    },
    "Qwen2.5-Coder-7B-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.65,
            "reasoning": 0.70,
            "tools": 0.70,
            "code": 0.95,
            "speed": 0.80,
        },
        "context_len": 131072,
        "ram_gb_q4": 5,
    },
    "Qwen2.5-Coder-32B-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.70,
            "reasoning": 0.80,
            "tools": 0.75,
            "code": 0.98,
            "speed": 0.45,
        },
        "context_len": 131072,
        "ram_gb_q4": 20,
    },
    # ---- Qwen 3.x line (newer, broadly stronger) ----
    "Qwen3.5-9B": {
        "kind": "chat",
        "scores": {
            "chat": 0.85,
            "reasoning": 0.75,
            "tools": 0.75,
            "code": 0.70,
            "speed": 0.75,
        },
        "context_len": 131072,
        "ram_gb_q4": 6,
    },
    "Qwen3.6-27B": {
        "kind": "chat",
        "scores": {
            "chat": 0.92,
            "reasoning": 0.85,
            "tools": 0.85,
            "code": 0.80,
            "speed": 0.50,
        },
        "context_len": 131072,
        "ram_gb_q4": 16,
    },
    "Qwen3.6-35B-A3B": {
        "kind": "chat",
        "scores": {
            "chat": 0.93,
            "reasoning": 0.88,
            "tools": 0.85,
            "code": 0.85,
            "speed": 0.70,
        },
        "context_len": 262144,
        "ram_gb_q4": 21,
    },  # MoE so speed is better than dense
    "Qwen3-Coder-30B-A3B-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.75,
            "reasoning": 0.85,
            "tools": 0.80,
            "code": 0.98,
            "speed": 0.70,
        },
        "context_len": 131072,
        "ram_gb_q4": 17,
    },
    # ---- Mistral ----
    "Mistral-7B-Instruct-v0.3": {
        "kind": "chat",
        "scores": {
            "chat": 0.78,
            "reasoning": 0.65,
            "tools": 0.65,
            "code": 0.65,
            "speed": 0.80,
        },
        "context_len": 32768,
        "ram_gb_q4": 4,
    },
    # ---- Llama family ----
    "Llama-3.2-1B-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.55,
            "reasoning": 0.40,
            "tools": 0.50,
            "code": 0.45,
            "speed": 0.98,
        },
        "context_len": 131072,
        "ram_gb_q4": 1,
    },
    "Llama-3.2-3B-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.70,
            "reasoning": 0.55,
            "tools": 0.65,
            "code": 0.55,
            "speed": 0.92,
        },
        "context_len": 131072,
        "ram_gb_q4": 2,
    },
    # ---- DeepSeek (reasoning + code) ----
    "DeepSeek-R1-Distill-Qwen-14B": {
        "kind": "reasoning",
        "scores": {
            "chat": 0.55,
            "reasoning": 0.95,
            "tools": 0.30,
            "code": 0.80,
            "speed": 0.35,
        },
        "context_len": 131072,
        "ram_gb_q4": 9,
    },
    "DeepSeek-Coder-V2-Lite-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.70,
            "reasoning": 0.75,
            "tools": 0.65,
            "code": 0.95,
            "speed": 0.70,
        },
        "context_len": 163840,
        "ram_gb_q4": 10,
    },
    # ---- Gemma ----
    "gemma-2-2b-it": {
        "kind": "chat",
        "scores": {
            "chat": 0.65,
            "reasoning": 0.50,
            "tools": 0.50,
            "code": 0.50,
            "speed": 0.95,
        },
        "context_len": 8192,
        "ram_gb_q4": 2,
    },
    "gemma-2-9b-it": {
        "kind": "chat",
        "scores": {
            "chat": 0.80,
            "reasoning": 0.70,
            "tools": 0.65,
            "code": 0.65,
            "speed": 0.75,
        },
        "context_len": 8192,
        "ram_gb_q4": 6,
    },
    "gemma-4-E2B-it": {
        "kind": "chat",
        "scores": {
            "chat": 0.78,
            "reasoning": 0.70,
            "tools": 0.65,
            "code": 0.65,
            "speed": 0.93,
        },
        "context_len": 32768,
        "ram_gb_q4": 3,
    },
    "gemma-4-E4B-it": {
        "kind": "chat",
        "scores": {
            "chat": 0.85,
            "reasoning": 0.78,
            "tools": 0.70,
            "code": 0.70,
            "speed": 0.80,
        },
        "context_len": 32768,
        "ram_gb_q4": 5,
    },
    # ---- Phi (small, fast, tool-friendly) ----
    "Phi-3.5-mini-instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.70,
            "reasoning": 0.65,
            "tools": 0.70,
            "code": 0.65,
            "speed": 0.92,
        },
        "context_len": 131072,
        "ram_gb_q4": 2,
    },
    # ---- Yi ----
    "Yi-1.5-9B-Chat": {
        "kind": "chat",
        "scores": {
            "chat": 0.78,
            "reasoning": 0.65,
            "tools": 0.60,
            "code": 0.60,
            "speed": 0.75,
        },
        "context_len": 4096,
        "ram_gb_q4": 6,
    },
    # ---- Code-specialized (older but useful) ----
    "codellama-13b-instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.55,
            "reasoning": 0.55,
            "tools": 0.45,
            "code": 0.85,
            "speed": 0.65,
        },
        "context_len": 16384,
        "ram_gb_q4": 8,
    },
    # ---- SmolLM2 (smallest viable assistant) ----
    "SmolLM2-1.7B-Instruct": {
        "kind": "chat",
        "scores": {
            "chat": 0.50,
            "reasoning": 0.35,
            "tools": 0.45,
            "code": 0.40,
            "speed": 0.98,
        },
        "context_len": 8192,
        "ram_gb_q4": 1,
    },
    # ---- Reasoning-focused open weights ----
    "openai_gpt-oss-20b": {
        "kind": "reasoning",
        "scores": {
            "chat": 0.65,
            "reasoning": 0.92,
            "tools": 0.55,
            "code": 0.75,
            "speed": 0.50,
        },
        "context_len": 131072,
        "ram_gb_q4": 11,
    },
    "nvidia_Nemotron-3-Nano-30B-A3B": {
        "kind": "reasoning",
        "scores": {
            "chat": 0.70,
            "reasoning": 0.90,
            "tools": 0.60,
            "code": 0.80,
            "speed": 0.70,
        },
        "context_len": 131072,
        "ram_gb_q4": 20,
    },  # MoE
    "Qwen3-365-A3B-Fallback": {
        "kind": "reasoning",
        "scores": {
            "chat": 0.85,
            "reasoning": 0.95,
            "tools": 0.80,
            "code": 0.85,
            "speed": 0.65,
        },
        "context_len": 262144,
        "ram_gb_q4": 18,
    },  # presumed MoE/A3B
    # ---- Embedders ----
    "nomic-embed-text-v1.5": {
        "kind": "embed",
        "scores": {},
        "context_len": 8192,
        "ram_gb_q4": 0.5,
    },
    # ---- Voice (STT/TTS) ----
    "whisper-base-en": {
        "kind": "stt",
        "scores": {},
        "context_len": 0,
        "ram_gb_q4": 0.2,
    },
    "whisper-base.en": {
        "kind": "stt",
        "scores": {},
        "context_len": 0,
        "ram_gb_q4": 0.2,
    },
    "piper-amy-en": {"kind": "tts", "scores": {}, "context_len": 0, "ram_gb_q4": 0.1},
    "piper-ryan-en": {"kind": "tts", "scores": {}, "context_len": 0, "ram_gb_q4": 0.1},
}

# Regex → partial scores update + kind, applied to unknown model names in order.
# First match wins for `kind`; score updates merge across all matches.
#
# IMPORTANT for Ollama-style names: Ollama models look like `llama3.1:latest`
# or `qwen2.5:14b` (lowercase, no "Instruct" tag) — the registry's HF-format
# prefixes don't match. The Ollama family patterns below catch them so they
# don't fall through to the last-resort neutral default. Order: more-specific
# patterns first (e.g. `coder` before bare family name).
# Score updates from later patterns OVERWRITE earlier ones (dict.update
# semantics). Order matters: put broad baselines first, narrower specializing
# patterns later so e.g. `qwen2.5-coder:32b` ends with the code-specialist
# scores, not the bare-family ones.
FALLBACK_PATTERNS: list[tuple[str, dict, str | None]] = [
    # ---- Voice / embed (kind-determining) — first match sets the kind ----
    (r"(?i)whisper", {}, "stt"),
    (r"(?i)piper", {}, "tts"),
    (r"(?i)nomic.*embed|.*-embed|embed-|^bge-", {}, "embed"),
    (r"(?i):embed|^text-embedding", {}, "embed"),  # Ollama / OpenAI styles
    # ---- Broad baselines (run FIRST so specifics can override) ----
    # Ollama family names — `<family><version>:<tag>` form, lowercase. Without
    # this, `llama3.1:latest` etc. fell through to neutral 0.5 defaults and
    # left Tools / Large Context slots empty for Ollama users (P1-CRIT-01).
    (
        r"(?i)^(llama|qwen|mistral|mixtral|phi|gemma|smollm|yi|deepseek|nemotron|openchat|starling|aya|tinyllama|granite|olmo)[\d.]*[:_-]?",
        {"chat": 0.75, "tools": 0.60, "speed": 0.75, "reasoning": 0.60, "code": 0.55},
        "chat",
    ),
    # Bare instruct / chat — generic HF naming
    (r"(?i)instruct|chat", {"chat": 0.70, "tools": 0.55}, "chat"),
    # ---- Specializing patterns (override the broad baseline above) ----
    # Code-specialist
    (
        r"(?i)coder?|code-|:.*coder|^codellama|^codestral",
        {"code": 0.85, "chat": 0.55, "tools": 0.55, "speed": 0.65},
        "chat",
    ),
    # Tool-trained (Hermes family — heavily tuned for function calling)
    (r"(?i)hermes", {"tools": 0.92, "chat": 0.83, "speed": 0.70}, "chat"),
    # Reasoning families — slow but deep; first kind-match wins so put after
    # general patterns but use a kind override
    (
        r"(?i)r1|distill|reasoning|deepthink",
        {"reasoning": 0.85, "speed": 0.35, "tools": 0.35},
        "reasoning",
    ),
    (
        r"(?i):.*-r1|gpt-oss",
        {"reasoning": 0.88, "speed": 0.45, "tools": 0.40},
        "reasoning",
    ),
]


def known(name: str) -> bool:
    """True iff `name` exactly matches a prefix in MODELS."""
    return _lookup_prefix(name) is not None


def _lookup_prefix(name: str) -> str | None:
    """Return the longest MODELS key that is a prefix of `name`, or None.

    Q4_K_M / Q5_K_M / Q8_0 / Q6 suffixes (and .gguf extensions) collapse to
    one canonical entry, e.g. `Qwen2.5-14B-Instruct-Q4_K_M.gguf` →
    `Qwen2.5-14B-Instruct`.
    """
    candidates = [k for k in MODELS if name.startswith(k)]
    return max(candidates, key=len) if candidates else None

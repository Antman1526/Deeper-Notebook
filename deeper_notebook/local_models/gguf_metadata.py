"""v0.8.39 — GGUF metadata extraction.

Two extraction paths:

1. **`gguf` library** — when installed, read `general.architecture`,
   `<arch>.context_length`, and the file's overall byte size. Same
   approach `desktop/launcher.py:_detect_gguf_context_length` already
   uses (v0.7.206), kept consistent so the launcher's auto-detect and
   the inventory page agree on what each file advertises.

2. **Filename heuristic** — when the `gguf` library isn't installed
   (older Python envs, minimal API installs), parse the well-known
   `{model}-{params}-{instruct?}-{quant}.gguf` pattern that all
   HuggingFace TheBloke / bartowski / lmstudio GGUFs follow. Quant
   detection works on filename alone (e.g. `Q4_K_M`); architecture
   is inferred from the model-name prefix (`qwen2.5` → `qwen2`,
   `hermes-3-8b` → `llama`, etc — best-effort, may be None).

The two paths are complementary: the library is authoritative when
available, the heuristic is a graceful degradation that keeps the UI
useful even on minimal installs.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GGUFMetadata:
    """Lightweight metadata bundle for a single GGUF file.

    All fields are best-effort; any may be None when unknown. The
    inventory + UI handle None gracefully (show "—" or just omit the
    column).
    """

    architecture: str | None
    context_length: int | None
    quant: str | None
    parameter_count_b: float | None  # in billions, e.g. 7.0 for Qwen2.5-7B
    file_size_bytes: int


# All llama.cpp quant schemes we know about. Match against UPPERCASE
# stem. Order: longest first so "Q4_K_M" wins over "Q4" in a string
# like "model-q4_k_m.gguf".
_QUANT_PATTERNS = [
    "Q8_0",
    "Q6_K",
    "Q5_K_M",
    "Q5_K_S",
    "Q5_1",
    "Q5_0",
    "Q4_K_M",
    "Q4_K_S",
    "Q4_1",
    "Q4_0",
    "Q3_K_L",
    "Q3_K_M",
    "Q3_K_S",
    "Q2_K",
    "IQ4_XS",
    "IQ3_XXS",
    "IQ2_XXS",
    "IQ1_S",
    "F16",
    "F32",
    "BF16",
]


def parse_quant_from_filename(filename: str) -> str | None:
    """Parse the llama.cpp quant scheme from a GGUF filename.

    Returns the canonical form (e.g. "Q4_K_M") when found, else None.
    Case-insensitive matching, longest-match-wins (so "Q4_K_M" beats
    "Q4" when both substrings are present)."""
    if not filename:
        return None
    upper = filename.upper()
    for q in _QUANT_PATTERNS:
        if q in upper:
            return q
    return None


# Best-effort parameter-count parse. Matches "7B", "13b", "1.5B" etc
# anywhere in the filename. Returns the leading numeric value as float
# (in billions). None when no match.
_PARAM_PAT = re.compile(r"(\d+(?:\.\d+)?)\s*[bB](?:[-_.]|$)")


def parse_param_count_b(filename: str) -> float | None:
    """Extract the model parameter count from a GGUF filename in billions.

    E.g. "qwen2.5-7b-instruct-q4_k_m.gguf" → 7.0. Returns None when no
    numeric-B token is present."""
    if not filename:
        return None
    m = _PARAM_PAT.search(filename)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _parse_arch_from_filename(filename: str) -> str | None:
    """Coarse architecture inference from filename prefix. Best-effort —
    `gguf` library lookup is preferred when available."""
    lower = filename.lower()
    # Order matters — more specific prefixes first.
    if "qwen" in lower:
        return "qwen2"
    if "hermes" in lower or "nous-" in lower:
        return "llama"
    if "llama" in lower:
        return "llama"
    if "mistral" in lower or "mixtral" in lower:
        return "llama"  # llama.cpp treats Mistral/Mixtral as llama arch
    if "phi" in lower:
        return "phi3"
    if "gemma" in lower:
        return "gemma"
    if "deepseek" in lower:
        return "deepseek2"
    if "command-r" in lower or "commandr" in lower:
        return "command-r"
    return None


def parse_gguf_metadata(path: Path) -> GGUFMetadata:
    """Read the metadata bundle for a single GGUF file.

    Always returns a GGUFMetadata (even on parse failure); fields that
    couldn't be determined are None. File size is always present —
    `os.stat` is the cheapest reliable thing we can do.

    The `gguf` library is OPTIONAL. When unavailable, falls back to
    filename heuristics. This means inventory works on minimal Python
    installs (no `gguf` dep) at the cost of authoritative metadata.
    """
    filename = path.name

    # Always-available fields.
    try:
        file_size = path.stat().st_size
    except OSError:
        file_size = 0

    quant = parse_quant_from_filename(filename)
    param_count = parse_param_count_b(filename)

    # Prefer the library — it's authoritative.
    arch: str | None = None
    n_ctx: int | None = None
    try:
        from gguf import GGUFReader  # type: ignore[import-not-found]

        reader = GGUFReader(str(path))

        arch_field = reader.get_field("general.architecture")
        if arch_field is not None:
            arch_parts = getattr(arch_field, "parts", None) or []
            arch_data = getattr(arch_field, "data", None) or []
            if arch_parts and arch_data:
                raw = arch_parts[arch_data[0]]
                try:
                    arch = bytes(raw).decode("utf-8", errors="ignore").strip() or None
                except Exception:
                    arch = None

        if arch:
            ctx_field = reader.get_field(f"{arch}.context_length")
            if ctx_field is not None:
                ctx_parts = getattr(ctx_field, "parts", None) or []
                ctx_data = getattr(ctx_field, "data", None) or []
                if ctx_parts and ctx_data:
                    val = ctx_parts[ctx_data[0]]
                    try:
                        n_ctx = int(val[0]) if hasattr(val, "__len__") else int(val)
                    except (TypeError, ValueError):
                        n_ctx = None
    except ImportError:
        # gguf library not installed — fall through to heuristic.
        pass
    except (OSError, struct.error, ValueError):
        # Corrupt file / unknown format — return what we have.
        pass
    except Exception:
        # Belt-and-braces: never let metadata parsing crash callers.
        pass

    # Fallback to filename for arch if the library didn't yield one.
    if arch is None:
        arch = _parse_arch_from_filename(filename)

    return GGUFMetadata(
        architecture=arch,
        context_length=n_ctx,
        quant=quant,
        parameter_count_b=param_count,
        file_size_bytes=file_size,
    )

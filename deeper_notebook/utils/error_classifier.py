"""
Error classification utility for LLM provider errors.

Maps raw exceptions from AI providers/Esperanto/LangChain to user-friendly
error messages and appropriate exception types.
"""

from loguru import logger

from deeper_notebook.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DeeperNotebookError,
    ExternalServiceError,
    NetworkError,
    RateLimitError,
)

# Classification rules: (keywords, exception_class, user_message or None to pass through)
_CLASSIFICATION_RULES: list[tuple[list[str], type[DeeperNotebookError], str | None]] = [
    # Authentication errors
    (
        ["authentication", "unauthorized", "invalid api key", "invalid_api_key", "401"],
        AuthenticationError,
        "Authentication failed. Please check your API key in Settings -> Credentials.",
    ),
    # Rate limit errors
    (
        ["rate limit", "rate_limit", "429", "too many requests", "quota exceeded"],
        RateLimitError,
        "Rate limit exceeded. Please wait a moment and try again.",
    ),
    # Model not found (pass through original message)
    (
        ["model not found", "does not exist", "model_not_found"],
        ConfigurationError,
        None,
    ),
    # Configuration errors from provision.py (pass through)
    (
        ["no model configured", "please go to settings"],
        ConfigurationError,
        None,
    ),
    # v0.7.66 — local-LLM "still loading" / "not ready" cases. The
    # bundled llama-cpp-python server returns HTTP 503 during model
    # load (cold-start can take 10-30 s for a 14B Q4 GGUF on M-series
    # silicon). Some OpenAI-compatible servers (LM Studio, vLLM)
    # return a 200 with a JSON `error` body saying "model not loaded".
    # The classifier saw those as a generic "AI service error" before;
    # they're actually a clear, transient, user-actionable state.
    (
        [
            "model not loaded",
            "model is loading",
            "still loading",
            "model loading",
            "model unavailable",
            "no model loaded",
            "not ready",
            "warming up",
        ],
        ExternalServiceError,
        "The local model is still loading. Please wait a few seconds and try again.",
    ),
    # Network errors. v0.7.66 — also catches the most common
    # local-deploy failure mode: the LLM server (llama-cpp-python or
    # Ollama) isn't running yet, so the very first request after launch
    # gets a connection-refused. The previous generic message ("check
    # your network connection") was misleading on a local-only build;
    # we now hint at the local server explicitly.
    (
        [
            "connecterror",
            "timeoutexception",
            "connection refused",
            "connection error",
            "timed out",
            "timeout",
        ],
        NetworkError,
        (
            "Could not reach the AI model server. If you're using a local "
            "model (llama.cpp / Ollama), make sure it's running. Otherwise "
            "check your network connection and provider URL."
        ),
    ),
    # Context length errors
    (
        [
            "context length",
            "token limit",
            "maximum context",
            "context_length_exceeded",
            "max_tokens",
        ],
        ExternalServiceError,
        "Content too large for the selected model. Try using a smaller selection or a model with a larger context window.",
    ),
    # Payload too large errors
    (
        ["413", "payload too large", "request entity too large"],
        ExternalServiceError,
        "The request payload is too large for the AI provider. Try reducing the content size or using a different model.",
    ),
    # Provider availability errors
    (
        [
            "500",
            "502",
            "503",
            "service unavailable",
            "overloaded",
            "internal server error",
        ],
        ExternalServiceError,
        "The AI provider is temporarily unavailable. Please try again in a few minutes.",
    ),
]


def classify_error(exception: BaseException) -> tuple[type[DeeperNotebookError], str]:
    """
    Classify a raw exception into a user-friendly error type and message.

    Args:
        exception: Any exception from LLM providers/Esperanto/LangChain

    Returns:
        Tuple of (exception_class, user_friendly_message)
    """
    error_str = str(exception).lower()
    error_type_name = type(exception).__name__.lower()
    combined = f"{error_type_name}: {error_str}"

    for keywords, exc_class, message in _CLASSIFICATION_RULES:
        for keyword in keywords:
            if keyword in combined:
                user_message = (
                    message if message is not None else _truncate(str(exception))
                )
                return exc_class, user_message

    # Unclassified error - log for future improvement
    logger.warning(f"Unclassified LLM error ({type(exception).__name__}): {exception}")
    return ExternalServiceError, f"AI service error: {_truncate(str(exception))}"


def _truncate(text: str, max_length: int = 200) -> str:
    """Truncate text to max_length to avoid leaking verbose internal details."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


# ---------------------------------------------------------------------------
# v0.8.38 — sidecar stderr-tail classification.
#
# Companion to `classify_error` above. `classify_error` maps Python
# exceptions raised inside the FastAPI process; `_classify_sidecar_error`
# maps the LAST FEW LINES of a sidecar subprocess's stderr to a
# user-actionable hint. The launcher's per-child `.tail` files (v0.8.38)
# preserve the bytes; the API's `/healthz/sidecars/{kind}/log` endpoint
# calls this to render a one-liner above the raw log in the UI badge
# popover, so users see "Model file not found at /path" instead of
# scanning 50 lines of llama.cpp output for the cause.
# ---------------------------------------------------------------------------

# Each pattern is checked against the JOINED stderr tail (case-insensitive
# substring match). Order matters — first match wins. Patterns are kept
# narrow + plain-substring so a future copy edit in upstream llama.cpp /
# Whisper / Piper output doesn't silently break detection. The catch-all
# at the end returns None so the popover falls back to showing the raw
# tail without a hint.
_SIDECAR_PATTERNS: list[tuple[str, str]] = [
    # llama.cpp / llama-cpp-python — most common chat-sidecar failures.
    (
        "failed to load model",
        "Model file could not be loaded — check the GGUF path and integrity.",
    ),
    ("file not found", "Model file not found — verify the path in your config."),
    (
        "no such file or directory",
        "Model file not found — verify the path in your config.",
    ),
    # OOM family — surfaces from CUDA, Metal, and CPU allocators differently.
    (
        "out of memory",
        "Out of memory — try a smaller / more-quantized model, or lower n_ctx.",
    ),
    ("cuda error", "GPU error — falling back to CPU may help; or restart the app."),
    (
        "metal error",
        "Apple GPU (Metal) error — restart the app or try a smaller model.",
    ),
    ("ggml-cuda", "CUDA backend failed — restart the app or switch to a CPU build."),
    # Port collision — common when two ONP instances or another local
    # server are running on the configured port.
    (
        "address already in use",
        "Port already in use — another process is holding it. Restart the app or change the port.",
    ),
    (
        "address in use",
        "Port already in use — another process is holding it. Restart the app or change the port.",
    ),
    (
        "eaddrinuse",
        "Port already in use — another process is holding it. Restart the app or change the port.",
    ),
    # llama-cpp-python launcher Python errors.
    (
        "modulenotfounderror",
        "Sidecar Python dependency missing — reinstall the desktop bundle.",
    ),
    (
        "importerror",
        "Sidecar Python dependency missing — reinstall the desktop bundle.",
    ),
    # Whisper / Piper specific.
    ("whisper.cpp:", "Whisper sidecar error — check the .pt model file is present."),
    ("piper:", "Piper TTS error — check the voice model file is present."),
    # Generic crash markers — least specific, must come last.
    (
        "segmentation fault",
        "Sidecar crashed (segfault) — possible model-file corruption.",
    ),
    ("killed: 9", "Sidecar was killed (likely by the OS for OOM)."),
]


def classify_sidecar_error(tail_text: str) -> str | None:
    """Map a sidecar's recent stderr tail to a user-friendly hint.

    Args:
        tail_text: The concatenated last ~50 lines of stderr captured by
            the launcher's `_start_tail_drainer` (v0.8.38).

    Returns:
        A short, action-oriented sentence the UI can show above the raw
        log, or None when no known pattern matches (UI shows the raw tail
        only — better than a misleading hint).

    The match is case-insensitive substring. Order in `_SIDECAR_PATTERNS`
    is significant: narrower patterns (e.g. specific GGUF/Metal errors)
    come before broader ones (e.g. generic "killed") so the most
    specific advice wins.
    """
    if not tail_text:
        return None
    haystack = tail_text.lower()
    for needle, hint in _SIDECAR_PATTERNS:
        if needle in haystack:
            return hint
    return None

from datetime import datetime, timezone

from langchain.tools import tool


# todo: turn this into a system prompt variable
@tool
def get_current_timestamp() -> str:
    """
    name: get_current_timestamp
    Returns the current timestamp in UTC as YYYYMMDDTHHmmssZ.
    """
    # v0.7.190 — was `datetime.now().strftime("%Y%m%d%H%M%S")` —
    # naive local time with no TZ marker. The return value lands in
    # LLM prompts that may be cached across machines and/or replayed
    # later; without UTC + Z marker, "20260522113000" is ambiguous
    # (was that local UTC-5 or local UTC+9?). The aware-UTC fix is
    # the companion to v0.7.187's ObjectModel.save() change.
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

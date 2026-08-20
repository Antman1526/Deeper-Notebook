"""Free localhost port discovery."""

from __future__ import annotations

import logging
import socket
from contextlib import ExitStack

log = logging.getLogger(__name__)


# v0.7.204 — bounded retry count for the find_free_ports race
# mitigation. Set generously low: a real collision is rare, but if
# we re-probe and STILL get a colliding port twice, something is
# pinning the allocator (e.g., a misbehaving OS allocator returning
# the same port repeatedly) and looping forever would be worse than
# failing fast.
_MAX_REPROBE_ATTEMPTS = 5


def _make_probe_socket() -> socket.socket:
    """Create a probe socket with SO_REUSEADDR set.

    v0.7.204 — SO_REUSEADDR on the probe sockets means a child
    process that subsequently binds to the same port (after we
    close the probe socket on function return) won't be blocked by
    a stray TIME_WAIT. Strictly speaking probe sockets that never
    accepted a connection don't go into TIME_WAIT, but the flag is
    harmless and matches the behavior of every real server we spawn
    (uvicorn, llama-cpp-python, surreal, Next.js).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except OSError:
        # Some platforms (Windows older releases) reject the flag on
        # SOCK_STREAM. The race mitigation degrades to "probe only"
        # which is exactly the pre-v0.7.204 behavior.
        pass
    return s


def find_free_port() -> int:
    with _make_probe_socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_free_ports(n: int) -> list[int]:
    """Allocate n distinct free ports atomically (sockets held until return).

    v0.7.204 — Adds SO_REUSEADDR on the probe sockets to reduce the
    window between socket-close (on function return) and the
    eventual subprocess `bind()` call. The previous implementation
    closed the probe sockets via the ExitStack on return, leaving a
    multi-second window during which another macOS / Windows
    process (Chrome, Spotlight Helper, the user's other dev server)
    could grab the port. SO_REUSEADDR doesn't eliminate the race
    but defeats the most common manifestation (TIME_WAIT from a
    very-recently-closed process on the same port).

    Also de-duplicates the returned ports — on rare OS allocator
    quirks the same ephemeral port can be returned to two
    different sockets before any of them bind for real. If a
    duplicate is observed, re-probe up to `_MAX_REPROBE_ATTEMPTS`
    times before giving up.
    """
    if n == 0:
        return []

    for attempt in range(_MAX_REPROBE_ATTEMPTS):
        with ExitStack() as stack:
            socks = [stack.enter_context(_make_probe_socket()) for _ in range(n)]
            for s in socks:
                s.bind(("127.0.0.1", 0))
            ports = [s.getsockname()[1] for s in socks]
            if len(set(ports)) == n:
                return ports
            log.warning(
                "find_free_ports: duplicate port detected (attempt "
                "%d/%d): %r — re-probing",
                attempt + 1,
                _MAX_REPROBE_ATTEMPTS,
                ports,
            )

    # All retries exhausted. Return the best-effort set; the launcher's
    # _wait_tcp / individual spawn helpers surface the resulting
    # collision in their own logs.
    log.error(
        "find_free_ports: exhausted %d re-probe attempts; returning "
        "potentially-colliding port set",
        _MAX_REPROBE_ATTEMPTS,
    )
    with ExitStack() as stack:
        socks = [stack.enter_context(_make_probe_socket()) for _ in range(n)]
        for s in socks:
            s.bind(("127.0.0.1", 0))
        return [s.getsockname()[1] for s in socks]

"""Free localhost port discovery."""
from __future__ import annotations

import socket
from contextlib import ExitStack


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_free_ports(n: int) -> list[int]:
    """Allocate n distinct free ports atomically (sockets held until return)."""
    if n == 0:
        return []
    with ExitStack() as stack:
        socks = [stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
                 for _ in range(n)]
        for s in socks:
            s.bind(("127.0.0.1", 0))
        return [s.getsockname()[1] for s in socks]

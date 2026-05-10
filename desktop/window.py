# desktop/window.py
"""PyWebView window wrapper. Opens a native window pointed at a URL and
calls a teardown callback on close."""
from __future__ import annotations

from typing import Callable

import webview


def open_window(url: str, on_close: Callable[[], None], title: str = "Open Notebook Plus",
                width: int = 1280, height: int = 800) -> None:
    """Blocking — returns when the user closes the window."""
    window = webview.create_window(title, url, width=width, height=height)
    window.events.closed += on_close
    webview.start()

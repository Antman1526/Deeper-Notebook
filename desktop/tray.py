# desktop/tray.py
"""PyWebView tray-icon menu for Deeper Notebook.

Note: pywebview's tray/menu support varies by platform. On macOS we use the
`webview.menu` API; on Windows pywebview's Tray support has shifted between
versions. For v0.3 we implement best-effort with a try/except wrapper —
silently no-ops if the host platform's API doesn't support the call we make.
"""

from __future__ import annotations

from typing import Callable


def install_tray(
    on_open_main: Callable[[], None],
    on_open_manager: Callable[[], None],
    on_quit: Callable[[], None],
    on_open_memory: Callable[[], None] | None = None,
) -> None:
    """Install a system tray icon with menu entries. Best-effort — silently
    no-ops if pywebview's host platform doesn't support tray menus.
    """
    try:
        import webview  # local import: keep tray-less environments importable
        from webview.menu import Menu, MenuAction

        actions = [
            MenuAction("Open Main Window", on_open_main),
            MenuAction("Manage Models…", on_open_manager),
        ]
        if on_open_memory is not None:
            actions.append(MenuAction("Memory…", on_open_memory))
        actions.append(MenuAction("Quit", on_quit))
        menu = [Menu("Deeper Notebook", actions)]
        webview.set_menu(menu)
    except Exception:
        # Tray/menu not supported on this build — silently skip.
        return

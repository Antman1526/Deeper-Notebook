"""PyWebView window wrapper. Opens a native window pointed at a URL and
calls a teardown callback on close. Optionally injects a theme stylesheet
into the loaded page so Radix-UI / CSS-var-aware components pick up the
user's chosen theme."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import webview

# Keep in sync with desktop/first_run/static/themes.css
_THEMES = {
    "light-blue":      {"bg": "#FFFFFF", "fg": "#1A2B3C", "primary": "#2D7FF9", "accent": "#5AB1FF", "border": "#D8E5F5"},
    "system":          {"bg": "#FFFFFF", "fg": "#1A2B3C", "primary": "#2D7FF9", "accent": "#5AB1FF", "border": "#D8E5F5"},
    "solarized-light": {"bg": "#FDF6E3", "fg": "#586E75", "primary": "#268BD2", "accent": "#2AA198", "border": "#D8D2BF"},
    "github-light":    {"bg": "#FFFFFF", "fg": "#24292F", "primary": "#0969DA", "accent": "#1F883D", "border": "#D0D7DE"},
    "paper":           {"bg": "#FBF8F1", "fg": "#2A2520", "primary": "#8B5A2B", "accent": "#C0853D", "border": "#DDD3BF"},
    "dark":            {"bg": "#0F1419", "fg": "#E5EBF2", "primary": "#5AB1FF", "accent": "#2D7FF9", "border": "#2A3540"},
    "solarized-dark":  {"bg": "#002B36", "fg": "#93A1A1", "primary": "#268BD2", "accent": "#2AA198", "border": "#14424F"},
    "dracula":         {"bg": "#282A36", "fg": "#F8F8F2", "primary": "#BD93F9", "accent": "#FF79C6", "border": "#44475A"},
    "nord":            {"bg": "#2E3440", "fg": "#ECEFF4", "primary": "#88C0D0", "accent": "#5E81AC", "border": "#4C566A"},
}


def _theme_injection_js(theme_id: str) -> str:
    t = _THEMES.get(theme_id, _THEMES["light-blue"])
    return f"""
    (function() {{
      var s = document.createElement('style');
      s.id = 'onp-theme-injection';
      s.textContent = `
        :root {{
          --background: {t['bg']};
          --foreground: {t['fg']};
          --primary: {t['primary']};
          --accent: {t['accent']};
          --border: {t['border']};
          --card: {t['bg']};
          --popover: {t['bg']};
          --muted: {t['border']};
        }}
        html, body {{ background: {t['bg']} !important; color: {t['fg']}; }}

        /* Open Notebook Plus — layout fixes for dropdown text overflow */
        [role="combobox"], button[role="combobox"] {{
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          min-width: 0;
        }}
        [role="combobox"] > span {{
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          display: block;
          flex: 1 1 auto;
          min-width: 0;
        }}
        /* Force the model-assignment grid columns to share equal width and clip */
        .grid > * {{ min-width: 0; }}
      `;
      document.head.appendChild(s);
    }})();
    """


def open_window(url: str, on_close: Callable[[], None],
                title: str = "Open Notebook Plus",
                width: int = 1280, height: int = 800,
                theme: str = "light-blue") -> None:
    """Blocking — returns when the user closes the window."""
    window = webview.create_window(title, url, width=width, height=height)
    window.events.closed += on_close
    def _on_loaded():
        try:
            window.evaluate_js(_theme_injection_js(theme))
        except Exception:
            pass  # best-effort; never crash on theme injection
    window.events.loaded += _on_loaded
    webview.start()

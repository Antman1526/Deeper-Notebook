"""PyWebView window wrapper. Opens a native window pointed at a URL and
calls a teardown callback on close. Optionally injects a theme stylesheet
into the loaded page so Radix-UI / CSS-var-aware components pick up the
user's chosen theme."""
from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Callable

import webview


def _voice_injection_js() -> str:
    """Read the voice-injection JS file content (bundled as data)."""
    static = Path(__file__).parent / "first_run" / "static" / "voice_injection.js"
    if static.exists():
        try:
            return static.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


def _memory_injection_js() -> str:
    """Read the memory-injection JS file content (bundled as data)."""
    static = Path(__file__).parent / "first_run" / "static" / "memory_injection.js"
    if static.exists():
        try:
            return static.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""

# Theme palettes — minimal source-of-truth per theme; full shadcn token set
# is derived in _theme_tokens() below. Adding a new theme = 9 hex values here.
#
# A note on contrast: muted_fg is computed to maintain WCAG AA contrast against
# bg (4.5:1 for normal text). Earlier versions only set 7 tokens and let
# upstream's defaults bleed through; that produced unreadable labels in the
# dark themes (the issue visible in the v0.4 screenshot).
_THEMES = {
    # --- Light themes ---
    "light-blue": {
        "is_dark": False,
        "bg": "#FFFFFF", "fg": "#1A2B3C",
        "card": "#FFFFFF", "muted": "#F1F5F9", "muted_fg": "#475569",
        "primary": "#2D7FF9", "primary_fg": "#FFFFFF",
        "accent": "#5AB1FF", "accent_fg": "#FFFFFF",
        "border": "#D8E5F5", "destructive": "#EF4444",
    },
    "system": {
        "is_dark": False,
        "bg": "#FFFFFF", "fg": "#1A2B3C",
        "card": "#FFFFFF", "muted": "#F1F5F9", "muted_fg": "#475569",
        "primary": "#2D7FF9", "primary_fg": "#FFFFFF",
        "accent": "#5AB1FF", "accent_fg": "#FFFFFF",
        "border": "#D8E5F5", "destructive": "#EF4444",
    },
    "solarized-light": {
        "is_dark": False,
        "bg": "#FDF6E3", "fg": "#073642",
        "card": "#FDF6E3", "muted": "#EEE8D5", "muted_fg": "#586E75",
        "primary": "#268BD2", "primary_fg": "#FDF6E3",
        "accent": "#2AA198", "accent_fg": "#FDF6E3",
        "border": "#D8D2BF", "destructive": "#DC322F",
    },
    "github-light": {
        "is_dark": False,
        "bg": "#FFFFFF", "fg": "#24292F",
        "card": "#FFFFFF", "muted": "#F6F8FA", "muted_fg": "#57606A",
        "primary": "#0969DA", "primary_fg": "#FFFFFF",
        "accent": "#1F883D", "accent_fg": "#FFFFFF",
        "border": "#D0D7DE", "destructive": "#CF222E",
    },
    "paper": {
        "is_dark": False,
        "bg": "#FBF8F1", "fg": "#2A2520",
        "card": "#FBF8F1", "muted": "#F0EBE0", "muted_fg": "#6B5F4D",
        "primary": "#8B5A2B", "primary_fg": "#FBF8F1",
        "accent": "#C0853D", "accent_fg": "#FBF8F1",
        "border": "#DDD3BF", "destructive": "#B91C1C",
    },
    # --- Dark themes ---
    "dark": {
        "is_dark": True,
        "bg": "#0F1419", "fg": "#E5EBF2",
        "card": "#1A2330", "muted": "#1F2A38", "muted_fg": "#B8C2D0",
        "primary": "#5AB1FF", "primary_fg": "#0F1419",
        "accent": "#2D7FF9", "accent_fg": "#FFFFFF",
        "border": "#2A3540", "destructive": "#F87171",
    },
    "solarized-dark": {
        "is_dark": True,
        "bg": "#002B36", "fg": "#EEE8D5",
        "card": "#073642", "muted": "#073642", "muted_fg": "#93A1A1",
        "primary": "#268BD2", "primary_fg": "#FDF6E3",
        "accent": "#2AA198", "accent_fg": "#FDF6E3",
        "border": "#14424F", "destructive": "#DC322F",
    },
    "dracula": {
        "is_dark": True,
        "bg": "#282A36", "fg": "#F8F8F2",
        "card": "#343746", "muted": "#3D4051", "muted_fg": "#C7C9D9",
        "primary": "#BD93F9", "primary_fg": "#282A36",
        "accent": "#FF79C6", "accent_fg": "#282A36",
        "border": "#44475A", "destructive": "#FF5555",
    },
    "nord": {
        "is_dark": True,
        "bg": "#2E3440", "fg": "#ECEFF4",
        "card": "#3B4252", "muted": "#434C5E", "muted_fg": "#D8DEE9",
        "primary": "#88C0D0", "primary_fg": "#2E3440",
        "accent": "#5E81AC", "accent_fg": "#ECEFF4",
        "border": "#4C566A", "destructive": "#BF616A",
    },
}


def _theme_tokens(theme_id: str) -> dict:
    """Expand a 9-key palette into the full 23-token shadcn variable set.

    Sidebar tokens get a slightly contrasted treatment so the left nav reads
    as a distinct region rather than blending into the body.
    """
    t = _THEMES.get(theme_id, _THEMES["light-blue"])
    bg, fg = t["bg"], t["fg"]
    card, muted, muted_fg = t["card"], t["muted"], t["muted_fg"]
    primary, primary_fg = t["primary"], t["primary_fg"]
    accent, accent_fg = t["accent"], t["accent_fg"]
    border, destructive = t["border"], t["destructive"]
    is_dark = t["is_dark"]

    # Sidebar slightly offset from the body. Light → a touch grayer.
    # Dark → a touch lighter so the sidebar is legible against the body.
    sidebar = card if is_dark else "#FAFBFC"

    return {
        # Body
        "--background": bg,
        "--foreground": fg,
        "--card": card,
        "--card-foreground": fg,
        "--popover": card,
        "--popover-foreground": fg,
        # Brand
        "--primary": primary,
        "--primary-foreground": primary_fg,
        # Secondary / muted / accent (used for chip + label colors)
        "--secondary": muted,
        "--secondary-foreground": fg,
        "--muted": muted,
        "--muted-foreground": muted_fg,
        "--accent": accent,
        "--accent-foreground": accent_fg,
        # Status
        "--destructive": destructive,
        "--destructive-foreground": "#FFFFFF",
        # Lines + focus
        "--border": border,
        "--input": border,
        "--ring": primary,
        # Sidebar
        "--sidebar": sidebar,
        "--sidebar-foreground": fg,
        "--sidebar-primary": primary,
        "--sidebar-primary-foreground": primary_fg,
        "--sidebar-accent": muted,
        "--sidebar-accent-foreground": fg,
        "--sidebar-border": border,
        "--sidebar-ring": primary,
    }


def _theme_injection_js(theme_id: str, memory_url: str | None = None,
                        remind_openchronicle: bool = False) -> str:
    tokens = _theme_tokens(theme_id)
    is_dark = _THEMES.get(theme_id, _THEMES["light-blue"])["is_dark"]
    var_decls = "\n          ".join(f"{k}: {v};" for k, v in tokens.items())
    # Force the .dark class on <html> only when the active theme is a dark one
    # — shadcn components use [data-theme] / .dark to swap their own variable
    # layer; we set the class explicitly so the user's theme choice wins.
    body_class_setup = (
        "document.documentElement.classList.add('dark');"
        if is_dark else
        "document.documentElement.classList.remove('dark');"
    )
    base_js = f"""
    (function() {{
      // P1-MED-08 audit fix: idempotent injection. On Next.js soft navigations
      // the loaded event fires repeatedly; if the theme hasn't changed there's
      // nothing to do. Skip re-injection when the prior <style data-theme="X">
      // matches the active theme.
      var THEME_ID = "{theme_id}";
      var prior = document.getElementById('onp-theme-injection');
      if (prior && prior.dataset.theme === THEME_ID) return;

      // Set theme mode class BEFORE injecting variables — shadcn checks .dark
      {body_class_setup}

      var s = document.createElement('style');
      s.id = 'onp-theme-injection';
      s.dataset.theme = THEME_ID;
      s.textContent = `
        /* Open Notebook Plus theme — full shadcn token override
           (overrides both light + dark default blocks in upstream globals.css) */
        :root,
        :root.dark,
        :root[data-theme] {{
          {var_decls}
        }}
        html, body {{
          background: {tokens['--background']} !important;
          color: {tokens['--foreground']};
        }}

        /* Layout fixes for dropdown text overflow */
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
        .grid > * {{ min-width: 0; }}
      `;
      if (prior) prior.remove();
      document.head.appendChild(s);
    }})();
    """
    voice_js = _voice_injection_js()
    # Append a script-tag injection so the voice JS runs after page DOM is ready.
    voice_injector = f"""
    (function() {{
        var s = document.createElement('script');
        s.textContent = {_json.dumps(voice_js)};
        document.head.appendChild(s);
    }})();
    """
    memory_js = _memory_injection_js()
    memory_globals = (
        f"window.ONP_MEMORY_URL = {_json.dumps(memory_url)};"
        f"window.ONP_REMIND_OPENCHRONICLE = {('true' if remind_openchronicle else 'false')};"
    )
    memory_injector = f"""
    (function() {{
        {memory_globals}
        var s = document.createElement('script');
        s.textContent = {_json.dumps(memory_js)};
        document.head.appendChild(s);
    }})();
    """
    return base_js + voice_injector + memory_injector


def open_window(url: str, on_close: Callable[[], None],
                title: str = "Open Notebook Plus",
                width: int = 1280, height: int = 800,
                theme: str = "light-blue",
                memory_url: str | None = None,
                remind_openchronicle: bool = False) -> None:
    """Blocking — returns when the user closes the window."""
    window = webview.create_window(title, url, width=width, height=height)
    window.events.closed += on_close
    def _on_loaded():
        try:
            window.evaluate_js(
                _theme_injection_js(theme, memory_url=memory_url,
                                    remind_openchronicle=remind_openchronicle))
        except Exception:
            pass  # best-effort; never crash on theme injection
    window.events.loaded += _on_loaded
    webview.start()

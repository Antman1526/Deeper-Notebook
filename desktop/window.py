"""PyWebView window wrapper. Opens a native window pointed at a URL and
calls a teardown callback on close. Optionally injects a theme stylesheet
into the loaded page so Radix-UI / CSS-var-aware components pick up the
user's chosen theme.

v0.6.5: `webview` is imported lazily inside open_window() so the pure-
function helpers in this module (_THEMES, _theme_tokens,
_theme_injection_js) can be tested without pywebview installed. The
desktop bundle's runtime path is unaffected — it calls open_window()
which still requires webview.
"""
from __future__ import annotations

import html as _html
import json as _json
import threading
import time
from pathlib import Path
from typing import Callable


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
    # --- Research Core OS palettes ---
    "research-core-dark": {"is_dark": True, "bg": "#071B1D", "fg": "#D8FFF8", "card": "#0B292B", "muted": "#12383A", "muted_fg": "#A3CEC8", "primary": "#2DD4BF", "primary_fg": "#041313", "accent": "#38BDF8", "accent_fg": "#041313", "border": "#225053", "destructive": "#FB7185"},
    "research-core-light": {"is_dark": False, "bg": "#F5FBF9", "fg": "#102A2A", "card": "#FFFFFF", "muted": "#E5F2EE", "muted_fg": "#526E69", "primary": "#0F766E", "primary_fg": "#FFFFFF", "accent": "#0284C7", "accent_fg": "#FFFFFF", "border": "#C9DED8", "destructive": "#DC2626"},
    "deep-ocean": {"is_dark": True, "bg": "#06151F", "fg": "#D8F3F8", "card": "#0B2432", "muted": "#123446", "muted_fg": "#9FC6CE", "primary": "#2DD4BF", "primary_fg": "#041619", "accent": "#38BDF8", "accent_fg": "#041619", "border": "#21485A", "destructive": "#FB7185"},
    "graphite-lab": {"is_dark": True, "bg": "#151A1D", "fg": "#EDF7F5", "card": "#20272B", "muted": "#2A3438", "muted_fg": "#B5C6C3", "primary": "#5EEAD4", "primary_fg": "#0D1718", "accent": "#67E8F9", "accent_fg": "#0D1718", "border": "#3B494E", "destructive": "#FB7185"},
    "arctic-research": {"is_dark": False, "bg": "#F4FAFC", "fg": "#122A35", "card": "#FFFFFF", "muted": "#E3EFF3", "muted_fg": "#4F6974", "primary": "#0F766E", "primary_fg": "#FFFFFF", "accent": "#0284C7", "accent_fg": "#FFFFFF", "border": "#C7DBE2", "destructive": "#DC2626"},
    "archive-paper": {"is_dark": False, "bg": "#F7F1E5", "fg": "#2B332E", "card": "#FFFDF8", "muted": "#ECE3D3", "muted_fg": "#665F52", "primary": "#0F766E", "primary_fg": "#FFFFFF", "accent": "#A16207", "accent_fg": "#FFFFFF", "border": "#D8CDBB", "destructive": "#B91C1C"},
    "high-contrast-dark": {"is_dark": True, "bg": "#000000", "fg": "#FFFFFF", "card": "#111111", "muted": "#1E1E1E", "muted_fg": "#E6E6E6", "primary": "#5EEAD4", "primary_fg": "#000000", "accent": "#67E8F9", "accent_fg": "#000000", "border": "#FFFFFF", "destructive": "#FF5A67"},
    "high-contrast-light": {"is_dark": False, "bg": "#FFFFFF", "fg": "#000000", "card": "#FFFFFF", "muted": "#EFEFEF", "muted_fg": "#333333", "primary": "#006B63", "primary_fg": "#FFFFFF", "accent": "#005FCC", "accent_fg": "#FFFFFF", "border": "#000000", "destructive": "#B00020"},
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
    # --- v0.8.72: premium theme pack ---------------------------------------
    # Eight popular, hand-tuned palettes. Each fg/bg clears WCAG AAA (7:1) and
    # each muted_fg/bg clears AA (4.5:1) — enforced by desktop/tests/test_window.py
    # (parametrized over every key here), so a future tweak can't silently
    # regress legibility. "midnight-aurora" is the signature theme: its
    # indigo→violet palette matches the launch splash + Aurora Reveal intro.
    "midnight-aurora": {  # dark · signature (matches splash/intro)
        "is_dark": True,
        "bg": "#0D0E1D", "fg": "#EEF0FF",
        "card": "#181A33", "muted": "#20223F", "muted_fg": "#B9BEE0",
        "primary": "#6C7BFF", "primary_fg": "#FFFFFF",
        "accent": "#B96CFF", "accent_fg": "#FFFFFF",
        "border": "#2A2D52", "destructive": "#FF6B8B",
    },
    "tokyo-night": {  # dark
        "is_dark": True,
        "bg": "#1A1B26", "fg": "#C0CAF5",
        "card": "#24283B", "muted": "#2F334D", "muted_fg": "#A9B1D6",
        "primary": "#7AA2F7", "primary_fg": "#1A1B26",
        "accent": "#BB9AF7", "accent_fg": "#1A1B26",
        "border": "#3B4261", "destructive": "#F7768E",
    },
    "catppuccin-mocha": {  # dark
        "is_dark": True,
        "bg": "#1E1E2E", "fg": "#CDD6F4",
        "card": "#313244", "muted": "#45475A", "muted_fg": "#A6ADC8",
        "primary": "#CBA6F7", "primary_fg": "#1E1E2E",
        "accent": "#F5C2E7", "accent_fg": "#1E1E2E",
        "border": "#45475A", "destructive": "#F38BA8",
    },
    "rose-pine": {  # dark
        "is_dark": True,
        "bg": "#191724", "fg": "#E0DEF4",
        "card": "#1F1D2E", "muted": "#26233A", "muted_fg": "#908CAA",
        "primary": "#C4A7E7", "primary_fg": "#191724",
        "accent": "#EBBCBA", "accent_fg": "#191724",
        "border": "#403D52", "destructive": "#EB6F92",
    },
    "gruvbox-dark": {  # dark
        "is_dark": True,
        "bg": "#282828", "fg": "#EBDBB2",
        "card": "#3C3836", "muted": "#504945", "muted_fg": "#BDAE93",
        "primary": "#FABD2F", "primary_fg": "#282828",
        "accent": "#FE8019", "accent_fg": "#282828",
        "border": "#504945", "destructive": "#FB4934",
    },
    "one-dark": {  # dark
        "is_dark": True,
        "bg": "#282C34", "fg": "#C5CCD6",
        "card": "#21252B", "muted": "#3B4048", "muted_fg": "#9AA2AF",
        "primary": "#61AFEF", "primary_fg": "#282C34",
        "accent": "#C678DD", "accent_fg": "#282C34",
        "border": "#3E4451", "destructive": "#E06C75",
    },
    "catppuccin-latte": {  # light
        "is_dark": False,
        "bg": "#EFF1F5", "fg": "#4C4F69",
        "card": "#FFFFFF", "muted": "#CCD0DA", "muted_fg": "#5C5F74",
        "primary": "#8839EF", "primary_fg": "#FFFFFF",
        "accent": "#1E66F5", "accent_fg": "#FFFFFF",
        "border": "#BCC0CC", "destructive": "#D20F39",
    },
    "rose-pine-dawn": {  # light
        "is_dark": False,
        "bg": "#FAF4ED", "fg": "#4B4661",
        "card": "#FFFAF3", "muted": "#F2E9E1", "muted_fg": "#6A6580",
        "primary": "#907AA9", "primary_fg": "#FAF4ED",
        "accent": "#D7827E", "accent_fg": "#FAF4ED",
        "border": "#DFDAD9", "destructive": "#B4637A",
    },
}


def _theme_tokens(theme_id: str) -> dict:
    """Expand a 9-key palette into the full 23-token shadcn variable set.

    Sidebar tokens get a slightly contrasted treatment so the left nav reads
    as a distinct region rather than blending into the body.
    """
    t = _THEMES.get(theme_id, _THEMES["research-core-dark"])
    bg, fg = t["bg"], t["fg"]
    card, muted, muted_fg = t["card"], t["muted"], t["muted_fg"]
    primary, primary_fg = t["primary"], t["primary_fg"]
    accent, accent_fg = t["accent"], t["accent_fg"]
    border, destructive = t["border"], t["destructive"]
    is_dark = t["is_dark"]

    # Sidebar slightly offset from the body. Light → a touch grayer.
    # Dark → a touch lighter so the sidebar is legible against the body.
    sidebar = card if is_dark else "#FAFBFC"
    warning = "#FBBF24" if is_dark else "#D97706"
    research_tokens = {
        "--dn-canvas": bg,
        "--dn-panel": card,
        "--dn-panel-raised": f"color-mix(in oklab, {card} 88%, {primary})",
        "--dn-separator": border,
        "--dn-focus": primary,
        "--dn-selection": f"color-mix(in oklab, {primary} 22%, transparent)",
        "--dn-evidence": accent,
        "--dn-warning": f"var(--warning, {warning})",
        "--dn-editable": primary,
        "--dn-read-only": muted_fg,
        "--dn-model-local": primary,
        "--dn-model-cloud": f"var(--info, {accent})",
        "--dn-graph-node": primary,
        "--dn-graph-edge": muted_fg,
        "--dn-graph-selected": accent,
    }

    return {
        **research_tokens,
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
                        remind_openchronicle: bool = False,
                        stt_url: str | None = None,
                        tts_url: str | None = None) -> str:
    """Inject ALL themes' tokens up front, keyed by [data-theme="X"]
    attribute selectors. The active theme is set by `dataset.theme` on
    <html>. The onp/ThemeSwitcher React component (and `window.ONP.setTheme`
    that we expose below) can switch themes live — instant, no reload.

    v0.5.7: previously baked a single theme into the CSS, so switching
    required re-evaluating the injection. With all themes present, switching
    is just changing one DOM attribute.
    """
    # Build a CSS block per theme: `:root[data-theme="X"] { ... }`
    blocks = []
    for tid, _meta in _THEMES.items():
        tokens = _theme_tokens(tid)
        decls = "\n          ".join(f"{k}: {v};" for k, v in tokens.items())
        # The default block (no data-theme attribute) uses the Research Core
        # palette so the page never flashes unstyled.
        if tid == "research-core-dark":
            blocks.append(f":root, :root[data-theme=\"{tid}\"] {{\n          {decls}\n        }}")
        else:
            blocks.append(f":root[data-theme=\"{tid}\"] {{\n          {decls}\n        }}")
    all_themes_css = "\n        ".join(blocks)
    initial = theme_id if theme_id in _THEMES else "research-core-dark"
    is_dark_map = {tid: ("true" if _THEMES[tid]["is_dark"] else "false") for tid in _THEMES}
    is_dark_js = ", ".join(f'"{tid}": {v}' for tid, v in is_dark_map.items())

    base_js = f"""
    (function() {{
      var INITIAL_THEME = "{initial}";
      // DN v0.5.7 — all themes live in CSS; live-switch via data-theme attr.
      // The same <style id="dn-theme-injection"> is reused across Next.js soft
      // navigations because the CSS block is theme-independent.
      if (!document.getElementById('dn-theme-injection')) {{
        var s = document.createElement('style');
        s.id = 'dn-theme-injection';
        s.textContent = `
        {all_themes_css}
        html, body {{
          background: var(--background) !important;
          color: var(--foreground);
        }}
        /* Layout fixes for dropdown text overflow */
        [role="combobox"], button[role="combobox"] {{
          overflow: hidden; text-overflow: ellipsis;
          white-space: nowrap; min-width: 0;
        }}
        [role="combobox"] > span {{
          overflow: hidden; text-overflow: ellipsis;
          white-space: nowrap; display: block;
          flex: 1 1 auto; min-width: 0;
        }}
        .grid > * {{ min-width: 0; }}
        `;
        document.head.appendChild(s);
      }}

      // Map of theme id → is_dark. Toggling the .dark class on <html> keeps
      // shadcn components that switch on `.dark` (not [data-theme]) in sync.
      var IS_DARK = {{ {is_dark_js} }};

      // Apply a theme: sets dataset.theme + .dark class. Internal — called
      // by both the initial-load path and window.DN.setTheme.
      function applyTheme(theme) {{
        if (!IS_DARK.hasOwnProperty(theme)) theme = "research-core-dark";
        document.documentElement.dataset.theme = theme;
        document.documentElement.classList.toggle('dark', IS_DARK[theme]);
      }}

      // Initial apply. INITIAL_THEME is baked from config.toml at the start
      // of every loaded event (open_window re-reads on each loaded), so we
      // pick up persistent changes across navigations.
      applyTheme(INITIAL_THEME);

      // Expose a switcher for the ThemeSwitcher React component. Sets the
      // attribute immediately for instant feedback, then POSTs to persist.
      // window.DN is the canonical desktop-wrapper namespace. Reuse an
      // existing legacy bridge during migration, then expose a deterministic
      // window.ONP alias for older renderer bundles.
      window.DN = window.DN || window.ONP || {{}};
      window.ONP = window.DN;
      window.DN.setTheme = function(theme) {{
        applyTheme(theme);
        try {{
          fetch('/api/deeper-notebook/theme', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{theme: theme}}),
          }}).catch(function() {{}});
        }} catch (e) {{}}
      }};
      window.DN.themes = Object.keys(IS_DARK);
      // v0.8.81 — one-click relaunch for the DB repair banner. Bridges to the
      // pywebview js_api; returns false in a plain browser (dev) so callers can
      // fall back. The native side reopens the app after this process exits.
      window.DN.relaunch = function() {{
        try {{
          if (window.pywebview && window.pywebview.api && window.pywebview.api.relaunch) {{
            window.pywebview.api.relaunch();
            return true;
          }}
        }} catch (e) {{}}
        return false;
      }};
    }})();
    """
    voice_js = _voice_injection_js()
    # v0.7.152 — Set canonical voice endpoints plus deterministic legacy
    # mirrors before the voice-injection script runs.
    #
    # Background: voice_injection.js defaults `STT_URL` to `/api/transcribe`
    # and `TTS_URL` to `/api/audio/speech`. Neither path exists on the main
    # FastAPI app — they're served by the per-launch whisper + piper shim
    # processes on dynamically-allocated ports. Without these globals the
    # mic button POSTs to a non-existent /api/transcribe (404) and the
    # voice-message TTS button POSTs to a non-existent /api/audio/speech
    # (404). Visible as "STT failed: HTTP 404" toast in the UI on every
    # mic press and a similarly-broken speaker icon.
    #
    # When stt_url/tts_url are None (e.g. whisper or piper failed to start
    # this session) we leave the globals UNSET so voice_injection.js falls
    # back to its built-in `/api/transcribe` default — which still 404s,
    # but at least the override mechanism doesn't make things worse. The
    # broken-state UX matches what the user already had.
    voice_globals_pieces: list[str] = []
    if stt_url:
        voice_globals_pieces.append(
            f"window.DEEPER_NOTEBOOK_STT_URL = {_json.dumps(stt_url)};"
            "window.ONP_STT_URL = window.DEEPER_NOTEBOOK_STT_URL;"
        )
    if tts_url:
        voice_globals_pieces.append(
            f"window.DEEPER_NOTEBOOK_TTS_URL = {_json.dumps(tts_url)};"
            "window.ONP_TTS_URL = window.DEEPER_NOTEBOOK_TTS_URL;"
        )
    voice_globals = "\n        ".join(voice_globals_pieces)
    # Append a script-tag injection so the voice JS runs after page DOM is ready.
    voice_injector = f"""
    (function() {{
        {voice_globals}
        var s = document.createElement('script');
        s.textContent = {_json.dumps(voice_js)};
        document.head.appendChild(s);
    }})();
    """
    memory_js = _memory_injection_js()
    # v0.7.210 — surface the running version to the frontend through the
    # canonical bridge plus a deterministic legacy mirror.
    try:
        from desktop import __version__ as _onp_version
    except Exception:
        _onp_version = "unknown"
    memory_globals = (
        f"window.DEEPER_NOTEBOOK_MEMORY_URL = {_json.dumps(memory_url)};"
        "window.ONP_MEMORY_URL = window.DEEPER_NOTEBOOK_MEMORY_URL;"
        "window.DEEPER_NOTEBOOK_REMIND_OPENCHRONICLE = "
        f"{('true' if remind_openchronicle else 'false')};"
        "window.ONP_REMIND_OPENCHRONICLE = "
        "window.DEEPER_NOTEBOOK_REMIND_OPENCHRONICLE;"
        f"window.DEEPER_NOTEBOOK_VERSION = {_json.dumps(_onp_version)};"
        "window.ONP_VERSION = window.DEEPER_NOTEBOOK_VERSION;"
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


def _app_recovery_injection_js(payload: dict[str, object]) -> str:
    """Render the packaged app's one-time, explicit bundle recovery card."""
    encoded = _json.dumps(payload).replace("<", "\\u003c").replace(">", "\\u003e")
    return f"""
    (function() {{
      var payload = {encoded};
      var existing = document.getElementById('deeper-app-recovery-card');
      if (!payload.show_recovery_card) {{
        if (existing) existing.remove();
        return;
      }}
      if (existing) return;

      var card = document.createElement('section');
      card.id = 'deeper-app-recovery-card';
      card.setAttribute('role', 'alertdialog');
      card.setAttribute('aria-label', payload.title);
      card.style.cssText = [
        'position:fixed', 'right:24px', 'bottom:24px', 'z-index:2147483647',
        'width:min(430px,calc(100vw - 48px))', 'padding:20px',
        'border:1px solid var(--border,#d8e5f5)', 'border-radius:14px',
        'background:var(--card,#fff)', 'color:var(--card-foreground,#1a2b3c)',
        'box-shadow:0 18px 55px rgba(15,23,42,.24)',
        'font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif'
      ].join(';');

      var title = document.createElement('h2');
      title.textContent = payload.title;
      title.style.cssText = 'font-size:17px;font-weight:700;margin:0 28px 8px 0';
      var message = document.createElement('p');
      message.textContent = payload.message;
      message.style.cssText = 'font-size:14px;line-height:1.5;margin:0 0 16px';
      var error = document.createElement('p');
      error.hidden = true;
      error.style.cssText = 'font-size:13px;color:#b91c1c;margin:0 0 12px';
      var actions = document.createElement('div');
      actions.style.cssText = 'display:flex;gap:10px;justify-content:flex-end';
      var keep = document.createElement('button');
      keep.type = 'button';
      keep.textContent = payload.keep_label;
      keep.style.cssText = 'padding:8px 12px;border:1px solid var(--border,#ccc);border-radius:8px;background:transparent;color:inherit';
      var replace = document.createElement('button');
      replace.type = 'button';
      replace.textContent = payload.replace_label;
      replace.style.cssText = 'padding:8px 12px;border:0;border-radius:8px;background:var(--primary,#2d7ff9);color:var(--primary-foreground,#fff);font-weight:600';
      var dismiss = document.createElement('button');
      dismiss.type = 'button';
      dismiss.textContent = '×';
      dismiss.setAttribute('aria-label', 'Keep both apps and dismiss');
      dismiss.style.cssText = 'position:absolute;top:10px;right:12px;border:0;background:transparent;color:inherit;font-size:22px';

      function keepBoth() {{
        Promise.resolve(window.pywebview.api.keep_both()).finally(function() {{
          card.remove();
        }});
      }}
      keep.addEventListener('click', keepBoth);
      dismiss.addEventListener('click', keepBoth);
      replace.addEventListener('click', function() {{
        if (!window.confirm(
          'Move Open Notebook Plus.app to the macOS Trash? ' +
          'Deeper Notebook.app will remain installed.'
        )) return;
        replace.disabled = true;
        Promise.resolve(window.pywebview.api.replace_old_app(true))
          .then(function(result) {{
            if (result && result.ok) {{
              card.remove();
              return;
            }}
            throw new Error((result && result.error) || 'Replacement was refused.');
          }})
          .catch(function(reason) {{
            error.textContent = String(reason && reason.message || reason);
            error.hidden = false;
            replace.disabled = false;
          }});
      }});

      actions.appendChild(keep);
      actions.appendChild(replace);
      card.appendChild(dismiss);
      card.appendChild(title);
      card.appendChild(message);
      card.appendChild(error);
      card.appendChild(actions);
      document.body.appendChild(card);
    }})();
    """


def _fit_window_size(screen_w: int, screen_h: int,
                     min_w: int, min_h: int, frac: float = 0.9) -> tuple[int, int]:
    """v0.8.67j — Pure helper: size the window to `frac` of the usable
    screen, never smaller than (min_w, min_h).

    Why: the main window opened at a fixed 1280x800, which felt cramped on
    large displays (the chat composer and three-pane layout had little
    room). Scaling to the screen makes it spacious on a big monitor while
    still fitting a small laptop (the floor guarantees it never shrinks
    below the previous default). When the screen can't be measured
    (screen_w/h <= 0), fall back to a generous fixed 1600x1000.
    """
    if screen_w <= 0 or screen_h <= 0:
        return max(min_w, 1600), max(min_h, 1000)
    return max(min_w, int(screen_w * frac)), max(min_h, int(screen_h * frac))


def _preferred_window_size(min_w: int, min_h: int) -> tuple[int, int]:
    """v0.8.67j — Screen-aware default size for the main window. Reads the
    macOS main-screen *visible* frame (excludes the menu bar + Dock) via
    AppKit, which pywebview's cocoa backend already depends on. Any failure
    (non-cocoa backend, headless) degrades to the fixed fallback in
    _fit_window_size — the window must always open.
    """
    try:
        from AppKit import NSScreen  # pyobjc — present on the cocoa backend
        vf = NSScreen.mainScreen().visibleFrame()
        return _fit_window_size(int(vf.size.width), int(vf.size.height),
                                min_w, min_h)
    except Exception:
        return _fit_window_size(0, 0, min_w, min_h)


# v0.8.68 — sentinel evaluated on every `loaded` event. True only on a real,
# non-404 app page: `window.__next_f` exists on every Next.js page (the
# splash and WebKit's error page have no Next runtime), and Next's own
# not-found page titles itself "404: …" (seen live — Next 16 standalone
# briefly serves its 404 for valid routes while route manifests lazy-load).
_FRONTEND_SENTINEL_JS = (
    "(!!window.__next_f) && !((document.title || '').indexOf('404') === 0)"
)


def _frontend_server_ready(url: str) -> bool:
    """One python-side probe of the page the webview will load.

    Unlike the splash's old in-page no-cors fetch, this sees the real
    status AND body — so Next's warm-up window, where it serves its
    not-found page (HTTP 200!) for valid routes, reads as not-ready.
    """
    import re

    import httpx

    try:
        r = httpx.get(url, timeout=2.0, follow_redirects=True)
    except Exception:
        return False
    if r.status_code >= 400:
        return False
    # v0.8.70 — Next.js 16 streams the global `notFound` boundary (including
    # its `.next-error-h1` style block) into the RSC payload of EVERY page, so
    # the old `b"next-error-h1" not in content` test was permanently False —
    # `_frontend_server_ready` never returned True, the splash→app handoff
    # never navigated the window, and the splash hung forever. Detect Next's
    # ACTUAL not-found page by its <title> ("404: This page could not be
    # found") instead, mirroring the JS sentinel (which checks that
    # document.title doesn't start with "404"). This still catches Next's
    # warm-up window, where valid routes briefly serve the 404 page at HTTP
    # 200. Require the Next runtime marker so a stray page can't false-pass.
    m = re.search(rb"<title>([^<]*)</title>", r.content)
    title = m.group(1).strip() if m else b""
    if title.startswith(b"404"):
        return False
    return b"__next_f" in r.content


def _start_handoff_controller(
    window,
    url: str,
    frontend_loaded: "threading.Event",
    splash_html: str,
    *,
    server_ready=None,
    min_splash_sec: float = 3.0,
    consecutive: int = 2,
    poll_sec: float = 0.4,
    attempt_timeout_sec: float = 6.0,
    max_attempts: int = 40,
    sleep=None,
    clock=None,
) -> "threading.Thread":
    """v0.8.68 — python-driven splash→app handoff with failure recovery.

    v0.8.72 — retry budget widened from 10×12s (~2 min) to 40×6s (~4 min).
    Live finding: on a slow ad-hoc cold boot WKWebView's `load_url` keeps
    failing ("This page couldn't load") for *minutes* even though the frontend
    server is provably serving (an httpx probe AND a manual webview Reload both
    succeed) — a known WebKit quirk where the probe passes but the real
    navigation races/fails. The old 10-attempt budget exhausted long before
    WKWebView became willing, so the controller gave up and the error page
    became the resting state; only a manual Reload recovered it. The wider
    budget keeps re-issuing the navigation (restoring the splash between tries,
    never the error page) until WKWebView finally loads the app — which a
    manual reload proves always eventually works. The shorter per-attempt
    timeout also shrinks how long a failed attempt's error page flashes before
    the splash is restored. (A stable code-signing identity keeps boots ~30s,
    where the very first attempt succeeds; this covers the ad-hoc slow path.)

    The first cut had the splash navigate itself after in-page no-cors
    probes; a probe can succeed and the subsequent real navigation still
    fail (seen live: WebKit's "This page couldn't load" with the server
    provably up), and an in-page probe cannot see HTTP status at all, so
    Next's warm-up 404 (status 200) read as "ready". This controller owns
    the whole handoff from python where everything is observable:

      1. wait until `server_ready(url)` passes `consecutive` times in a
         row AND the splash has been visible >= `min_splash_sec`;
      2. window.load_url(url);
      3. wait for the `loaded` handler to confirm a REAL app page (Next
         runtime present, not Next's 404) via `frontend_loaded`;
      4. on timeout — navigation failed or 404 rendered — put the splash
         BACK (instant, inline HTML) and retry from 1.

    The error page can therefore never be the resting state.
    """
    _sleep = sleep or time.sleep
    _clock = clock or time.monotonic
    _ready = server_ready or (lambda: _frontend_server_ready(url))

    def _drive() -> None:
        shown_at = _clock()
        for _attempt in range(max_attempts):
            streak = 0
            while streak < consecutive:
                streak = streak + 1 if _ready() else 0
                if streak >= consecutive:
                    break
                _sleep(poll_sec)
            remaining = min_splash_sec - (_clock() - shown_at)
            if remaining > 0:
                _sleep(remaining)
            try:
                window.load_url(url)
            except Exception:
                _sleep(poll_sec)
                continue  # window not ready yet — try again
            if frontend_loaded.wait(attempt_timeout_sec):
                return
            # Failed handoff (network error page or warm-up 404): restore
            # the splash so the user never rests on an error screen.
            try:
                window.load_html(splash_html)
            except Exception:
                pass
            shown_at = _clock()
        # Out of attempts: leave the frontend URL up so the manual Reload
        # still points somewhere useful.
        try:
            window.load_url(url)
        except Exception:
            pass

    t = threading.Thread(target=_drive, name="onp-handoff", daemon=True)
    t.start()
    return t


class _OnpJsApi:
    """v0.8.81 — pywebview js_api bridge, exposed to the page as
    `window.pywebview.api`. Currently just `relaunch()`, called by the DB
    repair banner's one-click "Repair & restart".

    relaunch() requests a flush-gated window close. Only after the window has
    actually closed and launcher cleanup has completed does
    complete_relaunch_after_close() spawn a detached helper that terminates
    this process and reopens the .app bundle. On the next boot the launcher's
    auto-repair (db_repair.auto_repair, backup-first) runs and clears the flag.
    It reopens exactly once (no relaunch loop). In dev (no .app bundle on the
    path) it just closes the window.

    v0.8.84 — FIX: the helper now ACTIVELY terminates the process (SIGTERM, then
    SIGKILL fallback) instead of passively waiting for it to exit. `window
    .destroy()` closes the webview window but does NOT make the launcher process
    exit (a non-daemon thread keeps it alive), so the old "wait for the pid to
    die, then open" helper waited forever and the app never reopened. SIGTERM
    lets the launcher's signal handler tear down its children first; the
    SIGKILL after a grace period is the backstop, and the reopened instance
    frees any stale ports on boot regardless.
    """

    def __init__(self, app_recovery=None) -> None:
        self._window = None  # set by open_window after create_window
        self._app_recovery = app_recovery
        self._relaunch_requested = False

    def get_app_recovery(self) -> dict[str, object]:
        if self._app_recovery is None:
            return {"show_recovery_card": False}
        return self._app_recovery.card_payload()

    def keep_both(self) -> dict[str, object]:
        if self._app_recovery is None:
            return {"ok": True, "kept_both": True}
        return self._app_recovery.keep_both()

    def replace_old_app(self, confirmed: bool = False) -> dict[str, object]:
        if self._app_recovery is None:
            return {"ok": False, "error": "App recovery is unavailable."}
        try:
            receipt = self._app_recovery.replace_old_app(confirmed=bool(confirmed))
        except Exception as error:
            from desktop.app_migration import AppReplacementOutcomeError

            if isinstance(error, AppReplacementOutcomeError):
                return {
                    "ok": False,
                    "move_outcome": error.move_outcome,
                    "error": error.user_message,
                }
            return {
                "ok": False,
                "move_outcome": "move-uncertain",
                "error": (
                    "App replacement could not be confirmed. Verify the macOS "
                    "Trash and Applications before trying again."
                ),
            }
        return {"ok": True, "receipt": str(receipt)}

    def relaunch(self) -> bool:  # pragma: no cover - exercised in-app only
        self._relaunch_requested = True
        try:
            if self._window is not None:
                self._window.destroy()
        except Exception:
            pass
        return True

    def complete_relaunch_after_close(
        self,
    ) -> bool:  # pragma: no cover - exercised in-app only
        import os
        import subprocess
        import sys

        if not self._relaunch_requested:
            return False
        self._relaunch_requested = False
        try:
            exe = Path(sys.executable)
            app_bundle = next((p for p in exe.parents if p.suffix == ".app"), None)
            if app_bundle is None:
                return False
            pid = os.getpid()
            sh = (
                f"/bin/sleep 1; "
                f"/bin/kill {pid} 2>/dev/null; "
                f"n=0; while /bin/kill -0 {pid} 2>/dev/null && [ $n -lt 20 ]; do "
                f"/bin/sleep 0.3; n=$((n+1)); done; "
                f"/bin/kill -9 {pid} 2>/dev/null; "
                f"/bin/sleep 0.5; "
                f'/usr/bin/open "{app_bundle}"'
            )
            subprocess.Popen(["/bin/sh", "-c", sh], start_new_session=True)
        except Exception:
            return False
        return True


_WORKSPACE_FLUSH_BEFORE_CLOSE_JS = """
(() => {
  const flush = window.DEEPER_NOTEBOOK_FLUSH_KNOWLEDGE_WORKSPACE;
  if (typeof flush !== 'function') {
    return Promise.resolve({ok: true, skipped: true});
  }
  return Promise.resolve(flush()).then((result) => {
    if (result && result.ok === true) return result;
    return {
      ok: false,
      error: result && result.error
        ? String(result.error)
        : 'Workspace persistence did not complete.',
    };
  }).catch((error) => ({
    ok: false,
    error: error && error.message
      ? String(error.message)
      : 'Workspace persistence failed.',
  }));
})()
"""


def _install_workspace_flush_close_gate(
    window,
    frontend_loaded: threading.Event,
    *,
    timeout_seconds: float = 5.0,
) -> None:
    """Delay native close until the frontend confirms workspace durability."""

    state_lock = threading.Lock()
    state = {
        "allow_close": False,
        "flush_in_progress": False,
        "timeout": None,
    }

    def _reset_failed_flush() -> None:
        with state_lock:
            state["flush_in_progress"] = False
            timer = state["timeout"]
            state["timeout"] = None
        if isinstance(timer, threading.Timer):
            timer.cancel()

    def _finish_close(result) -> None:
        if not isinstance(result, dict) or result.get("ok") is not True:
            _reset_failed_flush()
            return
        with state_lock:
            if state["allow_close"]:
                return
            state["allow_close"] = True
            state["flush_in_progress"] = False
            timer = state["timeout"]
            state["timeout"] = None
        if isinstance(timer, threading.Timer):
            timer.cancel()
        try:
            window.destroy()
        except Exception:
            pass

    def _on_timeout() -> None:
        _reset_failed_flush()

    def _evaluate_flush() -> None:
        try:
            window.evaluate_js(
                _WORKSPACE_FLUSH_BEFORE_CLOSE_JS,
                callback=_finish_close,
            )
        except Exception:
            _reset_failed_flush()

    def _on_closing():
        if not frontend_loaded.is_set():
            return None
        with state_lock:
            if state["allow_close"]:
                return None
            if state["flush_in_progress"]:
                return False
            state["flush_in_progress"] = True
            timeout = threading.Timer(timeout_seconds, _on_timeout)
            timeout.daemon = True
            state["timeout"] = timeout
        timeout.start()
        try:
            threading.Thread(
                target=_evaluate_flush,
                name="workspace-close-flush",
                daemon=True,
            ).start()
        except Exception:
            _reset_failed_flush()
        return False

    window.events.closing += _on_closing


def _install_native_termination_observer(
    on_terminate: Callable[[], None],
) -> Callable[[], None]:
    """Run launcher cleanup when Cocoa terminates the whole application.

    pywebview's ``window.events.closed`` covers a user closing the window, but
    AppKit termination requests (including ``NSRunningApplication.terminate``)
    can end the application without publishing that event. Observe the native
    notification as a second entry into the same idempotent cleanup path.
    """
    try:
        from AppKit import NSApplicationWillTerminateNotification
        from Foundation import NSNotificationCenter

        center = NSNotificationCenter.defaultCenter()
        token = center.addObserverForName_object_queue_usingBlock_(
            NSApplicationWillTerminateNotification,
            None,
            None,
            lambda _notification: on_terminate(),
        )
    except Exception:
        return lambda: None

    def _remove() -> None:
        try:
            center.removeObserver_(token)
        except Exception:
            pass

    return _remove


def _data_root_recovery_html(
    conflict_payload: dict[str, object],
) -> str:
    """Render only paths, aggregate hashes, and counts from conflict evidence."""

    def summary(name: str, label: str) -> str:
        value = conflict_payload.get(name)
        item = value if isinstance(value, dict) else {}
        path = _html.escape(str(item.get("path", "Unavailable")))
        tree_hash = _html.escape(str(item.get("tree_sha256", "Unavailable")))
        file_count = _html.escape(str(item.get("file_count", "Unavailable")))
        directory_count = _html.escape(
            str(item.get("directory_count", "Unavailable"))
        )
        return f"""
          <article class="root-summary">
            <h2>{_html.escape(label)}</h2>
            <dl>
              <dt>Path</dt><dd><code>{path}</code></dd>
              <dt>Tree SHA-256</dt><dd><code>{tree_hash}</code></dd>
              <dt>Files</dt><dd>{file_count}</dd>
              <dt>Directories</dt><dd>{directory_count}</dd>
            </dl>
          </article>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Deeper Notebook Recovery</title>
  <style>
    :root {{ color-scheme: light; font-family: -apple-system, BlinkMacSystemFont,
      "Segoe UI", sans-serif; background: #f4f7fb; color: #172033; }}
    body {{ margin: 0; padding: 40px; }}
    main {{ max-width: 960px; margin: 0 auto; }}
    h1 {{ margin: 0 0 12px; font-size: 30px; }}
    .notice {{ padding: 16px 18px; border: 1px solid #b7cae5;
      border-radius: 12px; background: #fff; line-height: 1.55; }}
    .summaries {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px; margin-top: 24px; }}
    .root-summary {{ min-width: 0; padding: 18px; border: 1px solid #d3deec;
      border-radius: 12px; background: #fff; }}
    .root-summary h2 {{ margin: 0 0 14px; font-size: 18px; }}
    dl {{ display: grid; grid-template-columns: max-content minmax(0, 1fr);
      gap: 10px 14px; margin: 0; }}
    dt {{ color: #526276; font-weight: 600; }}
    dd {{ min-width: 0; margin: 0; overflow-wrap: anywhere; }}
    code {{ font-size: 12px; }}
    @media (max-width: 720px) {{
      body {{ padding: 24px; }}
      .summaries {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Data folders need manual review</h1>
    <p class="notice">
      Deeper Notebook found different canonical and legacy data folders.
      Normal services were not started.
      No data root has been selected or changed.
      The summaries below contain paths, aggregate hashes, and counts only;
      neither folder will be merged, copied, or deleted here.
    </p>
    <section class="summaries" aria-label="Data root summaries">
      {summary("canonical", "Canonical data folder")}
      {summary("legacy", "Legacy data folder")}
    </section>
  </main>
</body>
</html>
"""


def open_data_root_recovery_window(
    *,
    conflict_payload: dict[str, object],
    app_recovery,
    storage_root: Path,
) -> None:
    """Open the isolated packaged recovery UI without resolving a data root."""
    import webview

    # Recovery has no browser state worth persisting. pywebview 5.4 defaults
    # to private mode, where cookies and local storage are ephemeral; passing
    # no storage_path eliminates the pathname consumer and its swap surface.
    del storage_root

    api = _OnpJsApi(app_recovery)
    window = webview.create_window(
        "Deeper Notebook Recovery",
        html=_data_root_recovery_html(conflict_payload),
        width=1080,
        height=760,
        js_api=api,
    )
    api._window = window

    def _on_loaded() -> None:
        try:
            window.evaluate_js(
                _app_recovery_injection_js(api.get_app_recovery())
            )
        except Exception:
            pass

    window.events.loaded += _on_loaded
    remove_termination_observer = _install_native_termination_observer(
        lambda: None
    )
    try:
        try:
            webview.start(private_mode=True)
        except TypeError:
            webview.start()
    finally:
        remove_termination_observer()


def open_window(url: str, on_close: Callable[[], None],
                title: str = "Deeper Notebook",
                width: int = 1280, height: int = 800,
                theme: str = "light-blue",
                memory_url: str | None = None,
                remind_openchronicle: bool = False,
                stt_url: str | None = None,
                tts_url: str | None = None,
                app_recovery=None,
                on_ready: Callable[[], None] | None = None) -> None:
    """Blocking — returns when the user closes the window.

    v0.7.152 — `stt_url` and `tts_url` are the dynamic per-launch endpoints
    of the whisper + piper shim processes. When set, they're injected as
    `window.ONP_STT_URL` / `window.ONP_TTS_URL` so the voice-injection
    JS calls the actual shims instead of POSTing to the non-existent
    `/api/transcribe` + `/api/audio/speech` routes (which were generating
    the "STT failed: HTTP 404" toasts in the UI).
    """
    import webview  # lazy: only the desktop runtime path needs this

    from desktop import window_state
    from desktop.data_root import active_data_root

    data_home = active_data_root()
    # v0.8.67m — reopen at the size you last left the window, if remembered;
    # otherwise v0.8.67j's screen-aware default. Clamp a remembered size to the
    # CURRENT screen so a size saved on a bigger monitor can't strand the
    # window off-screen. The width/height args remain the floor.
    saved = window_state.load_size(data_home)
    if saved is not None:
        try:
            from AppKit import NSScreen
            vf = NSScreen.mainScreen().visibleFrame()
            _sw, _sh = int(vf.size.width), int(vf.size.height)
        except Exception:
            _sw = _sh = 0
        win_w, win_h = window_state.clamp(
            saved[0], saved[1], _sw, _sh, min_w=width, min_h=height
        )
    else:
        # v0.8.67j — open at ~90% of the usable screen instead of a fixed
        # 1280x800 (which looked cramped on large monitors).
        win_w, win_h = _preferred_window_size(width, height)

    # v0.8.68 — open on the inline welcome splash instead of navigating
    # straight to the Next.js URL. The splash paints instantly (no network)
    # and the handoff controller below navigates to the app only once the
    # server demonstrably serves a real page — so a raced or hiccuping
    # first request can never strand the user on WKWebView's dead
    # "This page couldn't load" screen.
    from desktop.splash import build_splash_html

    splash_html = build_splash_html(url)
    # v0.8.81 — js_api bridge for window.pywebview.api.relaunch (DB repair
    # banner's "Repair & restart"). Window ref is set right after creation.
    _onp_api = _OnpJsApi(app_recovery)
    window = webview.create_window(
        title, html=splash_html, width=win_w, height=win_h, js_api=_onp_api
    )
    _onp_api._window = window

    # Track live size via the resize event when available (defensive: the event
    # name has varied across pywebview versions, so never let its absence break
    # the window). Falls back to the window's own width/height at close time.
    _live = {"w": win_w, "h": win_h}
    _cleanup_lock = threading.Lock()
    _cleanup_started = False

    def _notify_close_once() -> None:
        nonlocal _cleanup_started
        with _cleanup_lock:
            if _cleanup_started:
                return
            _cleanup_started = True
        on_close()

    try:
        def _on_resized(w, h):  # pragma: no cover - pywebview callback
            _live["w"], _live["h"] = int(w), int(h)
        window.events.resized += _on_resized
    except Exception:
        pass

    def _on_closed() -> None:  # pragma: no cover - pywebview callback
        # v0.8.67m — remember the final window size for next launch.
        try:
            window_state.save_size(
                data_home,
                getattr(window, "width", None) or _live["w"],
                getattr(window, "height", None) or _live["h"],
            )
        except Exception:
            pass
        _notify_close_once()
        _onp_api.complete_relaunch_after_close()

    window.events.closed += _on_closed

    _page_loaded = threading.Event()
    _ready_notified = False

    def _on_loaded():
        nonlocal _ready_notified
        # v0.8.68 — `loaded` fires for the splash, for WebKit's error page,
        # and for Next's warm-up 404 too (get_current_url() is None for
        # html= pages and reports the target URL even for failed loads, so
        # URL checks can't tell them apart — seen live). Ask the page
        # itself: only a document with the Next runtime that isn't titled
        # 404 confirms the handoff and warrants theme injection.
        try:
            on_app = bool(window.evaluate_js(_FRONTEND_SENTINEL_JS))
        except Exception:
            on_app = False
        if not on_app:
            return  # splash / error page / warm-up 404 — controller retries
        _page_loaded.set()  # confirms the handoff for the controller
        # v0.5.7 — re-read config.toml on every page load so live theme
        # switches via the canonical theme endpoint persist across navigations.
        # to the `theme` argument if the config can't be read.
        active_theme = theme
        try:
            from desktop.config import default_config_path, load_or_create
            active_theme = load_or_create(default_config_path()).theme
        except Exception:
            pass
        try:
            window.evaluate_js(
                _theme_injection_js(active_theme, memory_url=memory_url,
                                    remind_openchronicle=remind_openchronicle,
                                    stt_url=stt_url, tts_url=tts_url))
        except Exception:
            pass  # best-effort; never crash on theme injection
        try:
            window.evaluate_js(
                _app_recovery_injection_js(_onp_api.get_app_recovery())
            )
        except Exception:
            pass
        if not _ready_notified and on_ready is not None:
            _ready_notified = True
            on_ready()
    window.events.loaded += _on_loaded
    _install_workspace_flush_close_gate(window, _page_loaded)
    _start_handoff_controller(window, url, _page_loaded, splash_html)
    # v0.8.73 — PERSIST the webview's cookie/localStorage store across launches.
    # pywebview defaults to private_mode=True: an EPHEMERAL WKWebsiteDataStore
    # that is wiped on every app close. That silently broke every persisted
    # web-storage feature — most importantly the `wizard_completed` cookie never
    # survived a restart, so the first-launch Setup Wizard redirect fired on
    # EVERY launch (`/` → 307 → /setup-wizard), and the wizard's client-side
    # auto-skip (router.replace('/')) raced a cold boot straight into WebKit's
    # "This page couldn't load" — the exact reload-screen-every-launch the user
    # hit. (The same ephemeral wipe also reset the "show the intro once"
    # cookie.) Persisting to a stable path under ~/.deeper-notebook means the
    # wizard shows ONCE, the intro shows ONCE, and they stay dismissed across
    # launches AND across rebuilds (the stable code-signing identity keeps the
    # same data container).
    import os as _os
    _storage_path = str(data_home / "webview_data")
    try:
        _os.makedirs(_storage_path, exist_ok=True)
    except Exception:
        _storage_path = None
    try:
        remove_termination_observer = _install_native_termination_observer(
            _notify_close_once
        )
        try:
            webview.start(private_mode=False, storage_path=_storage_path)  # noqa: F821
        except TypeError:
            # Defensive: if a future pywebview drops these kwargs, fall back so the
            # app still launches (persistence degrades, but it won't crash).
            webview.start()  # noqa: F821
    finally:
        remove_termination_observer()

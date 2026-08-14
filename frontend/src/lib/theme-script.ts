import { isVisualSystemV2Enabled } from '@/lib/features'
import { DARK_THEME_IDS, getFreshThemeDefault, THEME_CATALOG } from '@/lib/themes/catalog'

const darkIds = JSON.stringify(DARK_THEME_IDS)
const validIds = JSON.stringify(THEME_CATALOG.map(theme => theme.id))
const freshDefault = getFreshThemeDefault(isVisualSystemV2Enabled())

// This script runs before React hydration to prevent theme flash.
export const themeScript = `
(function() {
  var root = document.documentElement;
  var validThemes = ${validIds};
  var darkThemes = ${darkIds};
  var freshDefault = '${freshDefault}';
  var displayDefaults = { wallpaper: 'aurora', motion: 'system', transparency: 'frosted', focusMode: false };
  var display = { wallpaper: displayDefaults.wallpaper, motion: displayDefaults.motion, transparency: displayDefaults.transparency, focusMode: displayDefaults.focusMode };

  try {
    var normalizeStoredTheme = function(value) {
      if (typeof value !== 'string' || value.length === 0) return null;
      if (value === 'light' || value === 'system' || validThemes.includes(value)) return value;
      return null;
    };
    var canonical = null;
    try { canonical = normalizeStoredTheme(localStorage.getItem('dn-theme')); } catch (error) { canonical = null; }
    var legacy = null;
    try { legacy = normalizeStoredTheme(localStorage.getItem('onp-theme')); } catch (error) { legacy = null; }
    var persisted = null;
    try {
      var persistedStorage = JSON.parse(localStorage.getItem('theme-storage') || '{}');
      var persistedState = persistedStorage && typeof persistedStorage === 'object' && persistedStorage.state && typeof persistedStorage.state === 'object'
        ? persistedStorage.state
        : {};
      persisted = normalizeStoredTheme(persistedState.theme);
    } catch (error) {
      persisted = null;
    }
    var theme = canonical || legacy || persisted || freshDefault;
    var systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (theme === 'light') theme = 'light-blue';
    if (theme === 'system') theme = systemDark ? 'dark' : 'light-blue';
    if (!validThemes.includes(theme)) theme = freshDefault;
    root.dataset.theme = theme;
    root.classList.toggle('dark', darkThemes.includes(theme));
  } catch (error) {
    root.dataset.theme = freshDefault;
    root.classList.toggle('dark', darkThemes.includes(freshDefault));
  }

  try {
    var storedDisplay = JSON.parse(localStorage.getItem('dn-display-preferences-v1') || '{}');
    var persistedDisplay = storedDisplay && typeof storedDisplay === 'object' && storedDisplay.state && typeof storedDisplay.state === 'object'
      ? storedDisplay.state
      : {};
    if (['aurora', 'static', 'off'].includes(persistedDisplay.wallpaper)) display.wallpaper = persistedDisplay.wallpaper;
    if (['system', 'full', 'reduced'].includes(persistedDisplay.motion)) display.motion = persistedDisplay.motion;
    if (['frosted', 'solid'].includes(persistedDisplay.transparency)) display.transparency = persistedDisplay.transparency;
    if (typeof persistedDisplay.focusMode === 'boolean') display.focusMode = persistedDisplay.focusMode;
  } catch (error) {
    display = { wallpaper: displayDefaults.wallpaper, motion: displayDefaults.motion, transparency: displayDefaults.transparency, focusMode: displayDefaults.focusMode };
  }

  var prefersReducedMotion = false;
  try {
    prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (error) {
    prefersReducedMotion = false;
  }

  var effectiveMotion = display.motion;
  if (prefersReducedMotion || display.motion === 'reduced') effectiveMotion = 'reduced';
  root.dataset.dnWallpaper = display.wallpaper;
  root.dataset.dnMotion = effectiveMotion;
  root.dataset.dnTransparency = display.transparency;
  root.dataset.dnFocusMode = display.focusMode ? 'true' : 'false';
})();
`

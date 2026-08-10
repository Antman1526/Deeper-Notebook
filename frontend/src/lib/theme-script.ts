import { DARK_THEME_IDS, DEFAULT_THEME_ID, THEME_CATALOG } from '@/lib/themes/catalog'

const darkIds = JSON.stringify(DARK_THEME_IDS)
const validIds = JSON.stringify(THEME_CATALOG.map(theme => theme.id))

// This script runs before React hydration to prevent theme flash.
export const themeScript = `
(function() {
  var root = document.documentElement;
  var displayDefaults = { wallpaper: 'aurora', motion: 'system', transparency: 'frosted' };
  var display = { wallpaper: displayDefaults.wallpaper, motion: displayDefaults.motion, transparency: displayDefaults.transparency };

  try {
    var canonical = localStorage.getItem('dn-theme');
    var legacy = localStorage.getItem('onp-theme');
    var persisted = JSON.parse(localStorage.getItem('theme-storage') || '{}').state?.theme;
    var theme = canonical || legacy || persisted || '${DEFAULT_THEME_ID}';
    var systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (theme === 'light') theme = 'light-blue';
    if (theme === 'system') theme = systemDark ? 'dark' : 'light-blue';
    var validThemes = ${validIds};
    if (!validThemes.includes(theme)) theme = '${DEFAULT_THEME_ID}';
    var darkThemes = ${darkIds};
    root.dataset.theme = theme;
    root.classList.toggle('dark', darkThemes.includes(theme));
  } catch (error) {
    root.dataset.theme = '${DEFAULT_THEME_ID}';
    root.classList.add('dark');
  }

  try {
    var storedDisplay = JSON.parse(localStorage.getItem('dn-display-preferences-v1') || '{}');
    var persistedDisplay = storedDisplay && typeof storedDisplay === 'object' && storedDisplay.state && typeof storedDisplay.state === 'object'
      ? storedDisplay.state
      : {};
    if (['aurora', 'static', 'off'].includes(persistedDisplay.wallpaper)) display.wallpaper = persistedDisplay.wallpaper;
    if (['system', 'full', 'reduced'].includes(persistedDisplay.motion)) display.motion = persistedDisplay.motion;
    if (['frosted', 'solid'].includes(persistedDisplay.transparency)) display.transparency = persistedDisplay.transparency;
  } catch (error) {
    display = { wallpaper: displayDefaults.wallpaper, motion: displayDefaults.motion, transparency: displayDefaults.transparency };
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
})();
`

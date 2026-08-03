import { DARK_THEME_IDS, DEFAULT_THEME_ID, THEME_CATALOG } from '@/lib/themes/catalog'

const darkIds = JSON.stringify(DARK_THEME_IDS)
const validIds = JSON.stringify(THEME_CATALOG.map(theme => theme.id))

// This script runs before React hydration to prevent theme flash.
export const themeScript = `
(function() {
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
    document.documentElement.dataset.theme = theme;
    document.documentElement.classList.toggle('dark', darkThemes.includes(theme));
  } catch (error) {
    document.documentElement.dataset.theme = '${DEFAULT_THEME_ID}';
    document.documentElement.classList.add('dark');
  }
})();
`

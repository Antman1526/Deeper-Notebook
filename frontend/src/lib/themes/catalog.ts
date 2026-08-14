export type ThemeGroup = 'featured' | 'light' | 'dark' | 'accessibility' | 'classics'

export const THEME_GROUPS: readonly { id: ThemeGroup; label: string }[] = [
  { id: 'featured', label: 'Featured' },
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
  { id: 'accessibility', label: 'Accessibility' },
  { id: 'classics', label: 'Classics' },
]

export interface ThemeDefinition {
  id: string
  label: string
  group: ThemeGroup
  dark: boolean
  description: string
  preview: {
    canvas: string
    panel: string
    text: string
    primary: string
    accent: string
    border: string
  }
}

export const LEGACY_DEFAULT_THEME_ID = 'research-core-dark' as const
export const VISUAL_SYSTEM_DEFAULT_THEME_ID = 'gemini-forward-light' as const
export const DEFAULT_THEME_ID = LEGACY_DEFAULT_THEME_ID

export const THEME_CATALOG = [
  { id: 'research-core-dark', label: 'Research Core Dark', group: 'featured', dark: true, description: 'Signature deep-teal research instrument.', preview: { canvas: '#071B1D', panel: '#0B292B', text: '#D8FFF8', primary: '#2DD4BF', accent: '#38BDF8', border: '#225053' } },
  { id: 'gemini-forward-light', label: 'Gemini-Forward Light', group: 'featured', dark: false, description: 'Airy mineral canvas with original indigo, violet, cyan, and mint research accents.', preview: { canvas: '#F7F7FC', panel: '#FFFFFF', text: '#202235', primary: '#5367D9', accent: '#7B5BD6', border: '#D9DDF0' } },
  { id: 'research-core-light', label: 'Research Core Light', group: 'featured', dark: false, description: 'Warm mineral paper with precise teal structure.', preview: { canvas: '#F5FBF9', panel: '#FFFFFF', text: '#102A2A', primary: '#0F766E', accent: '#0284C7', border: '#C9DED8' } },
  { id: 'deep-ocean', label: 'Deep Ocean', group: 'dark', dark: true, description: 'Navy depth with bioluminescent teal and cyan.', preview: { canvas: '#06151F', panel: '#0B2432', text: '#D8F3F8', primary: '#2DD4BF', accent: '#38BDF8', border: '#21485A' } },
  { id: 'graphite-lab', label: 'Graphite Lab', group: 'dark', dark: true, description: 'Neutral charcoal with restrained Research Core accents.', preview: { canvas: '#151A1D', panel: '#20272B', text: '#EDF7F5', primary: '#5EEAD4', accent: '#67E8F9', border: '#3B494E' } },
  { id: 'arctic-research', label: 'Arctic Research', group: 'light', dark: false, description: 'Cool white with glacial cyan focus.', preview: { canvas: '#F4FAFC', panel: '#FFFFFF', text: '#122A35', primary: '#0F766E', accent: '#0284C7', border: '#C7DBE2' } },
  { id: 'archive-paper', label: 'Archive Paper', group: 'light', dark: false, description: 'Warm archival paper with teal and brass accents.', preview: { canvas: '#F7F1E5', panel: '#FFFDF8', text: '#2B332E', primary: '#0F766E', accent: '#A16207', border: '#D8CDBB' } },
  { id: 'high-contrast-dark', label: 'High Contrast Dark', group: 'accessibility', dark: true, description: 'Maximum dark contrast and unambiguous states.', preview: { canvas: '#000000', panel: '#111111', text: '#FFFFFF', primary: '#5EEAD4', accent: '#67E8F9', border: '#FFFFFF' } },
  { id: 'high-contrast-light', label: 'High Contrast Light', group: 'accessibility', dark: false, description: 'Maximum light contrast and saturated focus.', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#000000', primary: '#006B63', accent: '#005FCC', border: '#000000' } },
  { id: 'light-blue', label: 'Light Blue', group: 'classics', dark: false, description: 'Original clean blue workspace.', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#1A2B3C', primary: '#2D7FF9', accent: '#5AB1FF', border: '#D8E5F5' } },
  { id: 'system', label: 'System', group: 'classics', dark: false, description: 'Follow the operating-system appearance.', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#1A2B3C', primary: '#2D7FF9', accent: '#5AB1FF', border: '#D8E5F5' } },
  { id: 'solarized-light', label: 'Solarized Light', group: 'light', dark: false, description: 'Low-glare cream with balanced blue and teal.', preview: { canvas: '#FDF6E3', panel: '#FDF6E3', text: '#073642', primary: '#268BD2', accent: '#2AA198', border: '#D8D2BF' } },
  { id: 'github-light', label: 'GitHub Light', group: 'light', dark: false, description: 'Crisp neutral workspace with familiar blue.', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#24292F', primary: '#0969DA', accent: '#1F883D', border: '#D0D7DE' } },
  { id: 'paper', label: 'Paper', group: 'light', dark: false, description: 'Warm cream reading environment.', preview: { canvas: '#FBF8F1', panel: '#FBF8F1', text: '#2A2520', primary: '#8B5A2B', accent: '#C0853D', border: '#DDD3BF' } },
  { id: 'catppuccin-latte', label: 'Catppuccin Latte', group: 'light', dark: false, description: 'Soft lavender-tinted light palette.', preview: { canvas: '#EFF1F5', panel: '#FFFFFF', text: '#4C4F69', primary: '#8839EF', accent: '#1E66F5', border: '#BCC0CC' } },
  { id: 'rose-pine-dawn', label: 'Rosé Pine Dawn', group: 'light', dark: false, description: 'Warm blush paper with muted violet.', preview: { canvas: '#FAF4ED', panel: '#FFFAF3', text: '#4B4661', primary: '#907AA9', accent: '#D7827E', border: '#DFDAD9' } },
  { id: 'dark', label: 'Dark', group: 'classics', dark: true, description: 'Original dark workspace with blue accents.', preview: { canvas: '#0F1419', panel: '#1A2330', text: '#E5EBF2', primary: '#5AB1FF', accent: '#2D7FF9', border: '#2A3540' } },
  { id: 'midnight-aurora', label: 'Midnight Aurora', group: 'classics', dark: true, description: 'Indigo and violet launch-era signature.', preview: { canvas: '#0D0E1D', panel: '#181A33', text: '#EEF0FF', primary: '#6C7BFF', accent: '#B96CFF', border: '#2A2D52' } },
  { id: 'tokyo-night', label: 'Tokyo Night', group: 'dark', dark: true, description: 'Deep navy with periwinkle focus.', preview: { canvas: '#1A1B26', panel: '#24283B', text: '#C0CAF5', primary: '#7AA2F7', accent: '#BB9AF7', border: '#3B4261' } },
  { id: 'catppuccin-mocha', label: 'Catppuccin Mocha', group: 'dark', dark: true, description: 'Soft dark violet with rose accents.', preview: { canvas: '#1E1E2E', panel: '#313244', text: '#CDD6F4', primary: '#CBA6F7', accent: '#F5C2E7', border: '#45475A' } },
  { id: 'rose-pine', label: 'Rosé Pine', group: 'dark', dark: true, description: 'Muted ink with lavender and rose.', preview: { canvas: '#191724', panel: '#1F1D2E', text: '#E0DEF4', primary: '#C4A7E7', accent: '#EBBCBA', border: '#403D52' } },
  { id: 'one-dark', label: 'One Dark', group: 'dark', dark: true, description: 'Editor-inspired graphite with blue and violet.', preview: { canvas: '#282C34', panel: '#21252B', text: '#C5CCD6', primary: '#61AFEF', accent: '#C678DD', border: '#3E4451' } },
  { id: 'gruvbox-dark', label: 'Gruvbox Dark', group: 'dark', dark: true, description: 'Earthy charcoal with amber emphasis.', preview: { canvas: '#282828', panel: '#3C3836', text: '#EBDBB2', primary: '#FABD2F', accent: '#FE8019', border: '#504945' } },
  { id: 'solarized-dark', label: 'Solarized Dark', group: 'dark', dark: true, description: 'Low-glare blue-green terminal palette.', preview: { canvas: '#002B36', panel: '#073642', text: '#EEE8D5', primary: '#268BD2', accent: '#2AA198', border: '#14424F' } },
  { id: 'dracula', label: 'Dracula', group: 'dark', dark: true, description: 'High-energy charcoal with violet and pink.', preview: { canvas: '#282A36', panel: '#343746', text: '#F8F8F2', primary: '#BD93F9', accent: '#FF79C6', border: '#44475A' } },
  { id: 'nord', label: 'Nord', group: 'dark', dark: true, description: 'Arctic charcoal with quiet blue focus.', preview: { canvas: '#2E3440', panel: '#3B4252', text: '#ECEFF4', primary: '#88C0D0', accent: '#5E81AC', border: '#4C566A' } },
] as const satisfies readonly ThemeDefinition[]

export type ThemeId = (typeof THEME_CATALOG)[number]['id']

export function getFreshThemeDefault(visualSystemEnabled: boolean): ThemeId {
  return visualSystemEnabled ? VISUAL_SYSTEM_DEFAULT_THEME_ID : LEGACY_DEFAULT_THEME_ID
}

export const THEME_BY_ID = Object.fromEntries(
  THEME_CATALOG.map(theme => [theme.id, theme]),
) as Record<ThemeId, (typeof THEME_CATALOG)[number]>

export const DARK_THEME_IDS = THEME_CATALOG.filter(theme => theme.dark).map(theme => theme.id)

export function isThemeId(value: string): value is ThemeId {
  return Object.prototype.hasOwnProperty.call(THEME_BY_ID, value)
}

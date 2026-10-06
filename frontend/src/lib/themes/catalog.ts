export type ThemeGroup = 'featured' | 'light' | 'dark' | 'accessibility' | 'classics'

export const THEME_GROUPS: readonly { id: ThemeGroup; labelKey: string }[] = [
  { id: 'featured', labelKey: 'workspace.catalog2.groupFeatured' },
  { id: 'light', labelKey: 'workspace.catalog2.groupLight' },
  { id: 'dark', labelKey: 'workspace.catalog2.groupDark' },
  { id: 'accessibility', labelKey: 'workspace.catalog2.groupAccessibility' },
  { id: 'classics', labelKey: 'workspace.catalog2.groupClassics' },
]

export interface ThemeDefinition {
  id: string
  /** English theme name; the render fallback and the name of a proper-noun theme. */
  label: string
  /**
   * i18n key for a theme whose name is an ordinary word ("System", "Dark").
   * Proper-noun themes (Dracula, Nord, ...) omit it and render `label` as is.
   */
  labelKey?: string
  group: ThemeGroup
  dark: boolean
  /** i18n key for the one-line theme description. */
  descriptionKey: string
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
  { id: 'research-core-dark', label: 'Research Core Dark', group: 'featured', dark: true, descriptionKey: 'workspace.catalog2.researchCoreDarkDescription', preview: { canvas: '#071B1D', panel: '#0B292B', text: '#D8FFF8', primary: '#2DD4BF', accent: '#38BDF8', border: '#225053' } },
  { id: 'gemini-forward-light', label: 'Gemini-Forward Light', group: 'featured', dark: false, descriptionKey: 'workspace.catalog2.geminiForwardLightDescription', preview: { canvas: '#F5F3EE', panel: '#FFFEFB', text: '#1E1C19', primary: '#3F4FC9', accent: '#7B5BD6', border: '#E6E1D7' } },
  {
    id: 'gemini-forward-dark',
    label: 'Gemini-Forward Dark',
    group: 'featured',
    dark: true,
    descriptionKey: 'workspace.catalog2.geminiForwardDarkDescription',
    preview: {
      canvas: '#12110F', panel: '#1B1A17', text: '#F3F1EC',
      primary: '#9AA5FF', accent: '#C59BFF', border: '#2F2D29',
    },
  },
  { id: 'research-core-light', label: 'Research Core Light', group: 'featured', dark: false, descriptionKey: 'workspace.catalog2.researchCoreLightDescription', preview: { canvas: '#F5FBF9', panel: '#FFFFFF', text: '#102A2A', primary: '#0F766E', accent: '#0284C7', border: '#C9DED8' } },
  { id: 'deep-ocean', label: 'Deep Ocean', group: 'dark', dark: true, descriptionKey: 'workspace.catalog2.deepOceanDescription', preview: { canvas: '#06151F', panel: '#0B2432', text: '#D8F3F8', primary: '#2DD4BF', accent: '#38BDF8', border: '#21485A' } },
  { id: 'graphite-lab', label: 'Graphite Lab', group: 'dark', dark: true, descriptionKey: 'workspace.catalog2.graphiteLabDescription', preview: { canvas: '#151A1D', panel: '#20272B', text: '#EDF7F5', primary: '#5EEAD4', accent: '#67E8F9', border: '#3B494E' } },
  { id: 'arctic-research', label: 'Arctic Research', group: 'light', dark: false, descriptionKey: 'workspace.catalog2.arcticResearchDescription', preview: { canvas: '#F4FAFC', panel: '#FFFFFF', text: '#122A35', primary: '#0F766E', accent: '#0284C7', border: '#C7DBE2' } },
  { id: 'archive-paper', label: 'Archive Paper', group: 'light', dark: false, descriptionKey: 'workspace.catalog2.archivePaperDescription', preview: { canvas: '#F7F1E5', panel: '#FFFDF8', text: '#2B332E', primary: '#0F766E', accent: '#A16207', border: '#D8CDBB' } },
  { id: 'high-contrast-dark', label: 'High Contrast Dark', labelKey: 'workspace.catalog2.themeNameHighContrastDark', group: 'accessibility', dark: true, descriptionKey: 'workspace.catalog2.highContrastDarkDescription', preview: { canvas: '#000000', panel: '#111111', text: '#FFFFFF', primary: '#5EEAD4', accent: '#67E8F9', border: '#FFFFFF' } },
  { id: 'high-contrast-light', label: 'High Contrast Light', labelKey: 'workspace.catalog2.themeNameHighContrastLight', group: 'accessibility', dark: false, descriptionKey: 'workspace.catalog2.highContrastLightDescription', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#000000', primary: '#006B63', accent: '#005FCC', border: '#000000' } },
  { id: 'light-blue', label: 'Light Blue', labelKey: 'workspace.catalog2.themeNameLightBlue', group: 'classics', dark: false, descriptionKey: 'workspace.catalog2.lightBlueDescription', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#1A2B3C', primary: '#2D7FF9', accent: '#5AB1FF', border: '#D8E5F5' } },
  { id: 'system', label: 'System', labelKey: 'workspace.catalog2.themeNameSystem', group: 'classics', dark: false, descriptionKey: 'workspace.catalog2.systemDescription', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#1A2B3C', primary: '#2D7FF9', accent: '#5AB1FF', border: '#D8E5F5' } },
  { id: 'solarized-light', label: 'Solarized Light', group: 'light', dark: false, descriptionKey: 'workspace.catalog2.solarizedLightDescription', preview: { canvas: '#FDF6E3', panel: '#FDF6E3', text: '#073642', primary: '#268BD2', accent: '#2AA198', border: '#D8D2BF' } },
  { id: 'github-light', label: 'GitHub Light', group: 'light', dark: false, descriptionKey: 'workspace.catalog2.githubLightDescription', preview: { canvas: '#FFFFFF', panel: '#FFFFFF', text: '#24292F', primary: '#0969DA', accent: '#1F883D', border: '#D0D7DE' } },
  { id: 'paper', label: 'Paper', labelKey: 'workspace.catalog2.themeNamePaper', group: 'light', dark: false, descriptionKey: 'workspace.catalog2.paperDescription', preview: { canvas: '#FBF8F1', panel: '#FBF8F1', text: '#2A2520', primary: '#8B5A2B', accent: '#C0853D', border: '#DDD3BF' } },
  { id: 'catppuccin-latte', label: 'Catppuccin Latte', group: 'light', dark: false, descriptionKey: 'workspace.catalog2.catppuccinLatteDescription', preview: { canvas: '#EFF1F5', panel: '#FFFFFF', text: '#4C4F69', primary: '#8839EF', accent: '#1E66F5', border: '#BCC0CC' } },
  { id: 'rose-pine-dawn', label: 'Rosé Pine Dawn', group: 'light', dark: false, descriptionKey: 'workspace.catalog2.rosePineDawnDescription', preview: { canvas: '#FAF4ED', panel: '#FFFAF3', text: '#4B4661', primary: '#907AA9', accent: '#D7827E', border: '#DFDAD9' } },
  { id: 'dark', label: 'Dark', labelKey: 'workspace.catalog2.themeNameDark', group: 'classics', dark: true, descriptionKey: 'workspace.catalog2.darkDescription', preview: { canvas: '#0F1419', panel: '#1A2330', text: '#E5EBF2', primary: '#5AB1FF', accent: '#2D7FF9', border: '#2A3540' } },
  { id: 'midnight-aurora', label: 'Midnight Aurora', group: 'classics', dark: true, descriptionKey: 'workspace.catalog2.midnightAuroraDescription', preview: { canvas: '#0D0E1D', panel: '#181A33', text: '#EEF0FF', primary: '#6C7BFF', accent: '#B96CFF', border: '#2A2D52' } },
  { id: 'tokyo-night', label: 'Tokyo Night', group: 'dark', dark: true, descriptionKey: 'workspace.catalog2.tokyoNightDescription', preview: { canvas: '#1A1B26', panel: '#24283B', text: '#C0CAF5', primary: '#7AA2F7', accent: '#BB9AF7', border: '#3B4261' } },
  { id: 'catppuccin-mocha', label: 'Catppuccin Mocha', group: 'dark', dark: true, descriptionKey: 'workspace.catalog2.catppuccinMochaDescription', preview: { canvas: '#1E1E2E', panel: '#313244', text: '#CDD6F4', primary: '#CBA6F7', accent: '#F5C2E7', border: '#45475A' } },
  { id: 'rose-pine', label: 'Rosé Pine', group: 'dark', dark: true, descriptionKey: 'workspace.catalog2.rosePineDescription', preview: { canvas: '#191724', panel: '#1F1D2E', text: '#E0DEF4', primary: '#C4A7E7', accent: '#EBBCBA', border: '#403D52' } },
  { id: 'one-dark', label: 'One Dark', group: 'dark', dark: true, descriptionKey: 'workspace.catalog2.oneDarkDescription', preview: { canvas: '#282C34', panel: '#21252B', text: '#C5CCD6', primary: '#61AFEF', accent: '#C678DD', border: '#3E4451' } },
  { id: 'gruvbox-dark', label: 'Gruvbox Dark', group: 'dark', dark: true, descriptionKey: 'workspace.catalog2.gruvboxDarkDescription', preview: { canvas: '#282828', panel: '#3C3836', text: '#EBDBB2', primary: '#FABD2F', accent: '#FE8019', border: '#504945' } },
  { id: 'solarized-dark', label: 'Solarized Dark', group: 'dark', dark: true, descriptionKey: 'workspace.catalog2.solarizedDarkDescription', preview: { canvas: '#002B36', panel: '#073642', text: '#EEE8D5', primary: '#268BD2', accent: '#2AA198', border: '#14424F' } },
  { id: 'dracula', label: 'Dracula', group: 'dark', dark: true, descriptionKey: 'workspace.catalog2.draculaDescription', preview: { canvas: '#282A36', panel: '#343746', text: '#F8F8F2', primary: '#BD93F9', accent: '#FF79C6', border: '#44475A' } },
  { id: 'nord', label: 'Nord', group: 'dark', dark: true, descriptionKey: 'workspace.catalog2.nordDescription', preview: { canvas: '#2E3440', panel: '#3B4252', text: '#ECEFF4', primary: '#88C0D0', accent: '#5E81AC', border: '#4C566A' } },
] as const satisfies readonly ThemeDefinition[]

/** The theme's display name: translated for generic names, the proper noun otherwise. */
export function themeLabel(
  theme: Pick<ThemeDefinition, 'label' | 'labelKey'>,
  t: (key: string) => string,
): string {
  return theme.labelKey ? t(theme.labelKey) : theme.label
}

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

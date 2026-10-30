// v0.8.130 — one dynamic import per locale, so each language is its own chunk. The
// app bundled all 14 (a 2.8 MB chunk on every page); now it ships English and loads
// the active language on demand. `resources` in ./index still imports every locale
// for the parity tests; the app must not import it.
type Translation = Record<string, unknown>

export const localeLoaders: Record<string, () => Promise<Translation>> = {
  'en-US': () => import('./en-US').then((module) => module.enUS),
  'zh-CN': () => import('./zh-CN').then((module) => module.zhCN),
  'zh-TW': () => import('./zh-TW').then((module) => module.zhTW),
  'pt-BR': () => import('./pt-BR').then((module) => module.ptBR),
  'ja-JP': () => import('./ja-JP').then((module) => module.jaJP),
  'it-IT': () => import('./it-IT').then((module) => module.itIT),
  'fr-FR': () => import('./fr-FR').then((module) => module.frFR),
  'ru-RU': () => import('./ru-RU').then((module) => module.ruRU),
  'bn-IN': () => import('./bn-IN').then((module) => module.bnIN),
  'ca-ES': () => import('./ca-ES').then((module) => module.caES),
  'es-ES': () => import('./es-ES').then((module) => module.esES),
  'de-DE': () => import('./de-DE').then((module) => module.deDE),
  'pl-PL': () => import('./pl-PL').then((module) => module.plPL),
  'tr-TR': () => import('./tr-TR').then((module) => module.trTR),
}

export const SUPPORTED_LANGUAGES = Object.keys(localeLoaders)

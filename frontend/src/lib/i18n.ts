import i18n, { type BackendModule } from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { enUS } from './locales/en-US'
import { localeLoaders, SUPPORTED_LANGUAGES } from './locales/loaders'

// v0.8.130 — English is bundled (it is also the fallback); every other language is
// fetched when selected. I18nProvider keeps the page hidden until it has arrived.
const lazyLocales: BackendModule = {
  type: 'backend',
  init() {},
  read(language, _namespace, callback) {
    const load = localeLoaders[language]
    if (!load) {
      callback(null, {})
      return
    }
    load().then((translation) => callback(null, translation), (error: Error) => callback(error, null))
  },
}

i18n
  .use(lazyLocales)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { 'en-US': { translation: enUS } },
    partialBundledLanguages: true,
    supportedLngs: SUPPORTED_LANGUAGES,
    load: 'currentOnly',
    fallbackLng: 'en-US',
    interpolation: {
      escapeValue: false, // react already safes from xss
    },
    react: {
      useSuspense: false,
      // Re-render when a lazily loaded language arrives, not only on a language change.
      bindI18n: 'languageChanged loaded',
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
  })

export default i18n

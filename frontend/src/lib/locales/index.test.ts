import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { resources } from './index'
import { enUS } from './en-US'

const getKeys = (obj: Record<string, unknown>, prefix = ''): string[] => {
  return Object.keys(obj).reduce((res: string[], el) => {
    const val = obj[el]
    if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
      return [...res, ...getKeys(val as Record<string, unknown>, prefix + el + '.')]
    }
    return [...res, prefix + el]
  }, [])
}

describe('Locale Parity', () => {
  const enKeys = getKeys(enUS)

  const locales = Object.entries(resources).filter(([code]) => code !== 'en-US')

  it.each(locales.map(([code, resource]) => [code, resource] as const))(
    '%s should have the same keys as en-US',
    (code, resource) => {
      const localeKeys = getKeys(resource.translation as Record<string, unknown>)

      const missing = enKeys.filter(key => !localeKeys.includes(key))
      const extra = localeKeys.filter(key => !enKeys.includes(key))

      expect(missing, `Missing keys in ${code}: ${missing.join(', ')}`).toEqual([])
      expect(extra, `Extra keys in ${code}: ${extra.join(', ')}`).toEqual([])
    },
  )
})

const getTranslation = (translation: Record<string, unknown>, key: string): unknown =>
  key.split('.').reduce<unknown>((value, segment) => (
    value !== null && typeof value === 'object'
      ? (value as Record<string, unknown>)[segment]
      : undefined
  ), translation)

const knowledgeExplorerKeys = (): string[] => {
  const srcDir = path.resolve(__dirname, '../../..')
  const explorerFiles = [
    'src/components/vault/KnowledgeExplorer.tsx',
    'src/components/vault/VaultFileTree.tsx',
    'src/components/vault/VaultGraph.tsx',
    'src/components/vault/VaultLinks.tsx',
  ]

  return [...new Set(explorerFiles.flatMap(file => {
    const source = fs.readFileSync(path.join(srcDir, file), 'utf-8')
    return [...source.matchAll(/\bt\(['"](knowledge\.[^'"]+)['"]\)/g)].map(match => match[1])
  }))].sort()
}

describe('Knowledge Explorer locale resolution', () => {
  const keys = knowledgeExplorerKeys()

  it('discovers the exact knowledge keys used by the Explorer components', () => {
    expect(keys).not.toEqual([])
  })

  it.each(Object.entries(resources))(
    '%s resolves every Knowledge Explorer key directly in its translation object',
    (code, resource) => {
      for (const key of keys) {
        const value = getTranslation(resource.translation as Record<string, unknown>, key)

        expect(value, `${code} is missing ${key}`).toEqual(expect.any(String))
        expect((value as string).trim(), `${code} has an empty ${key}`).not.toBe('')
        expect(value, `${code} falls back to the untranslated key ${key}`).not.toBe(key)
      }
    },
  )
})

const editorModeLocaleKeys = [
  'source',
  'livePreview',
  'emptyNote',
  'pageInvalid',
  'canonicalPathUnavailable',
  'pagePreview',
  'previewUnavailable',
  'footnotes',
  'sourceProvenance',
  'lineEnding',
  'encoding',
  'contentHash',
  'readOnlyMode',
  'headingLevel',
] as const

// These strings are public contracts of shared vault surfaces whose component
// ownership is split across the editor-mode tasks. Keep them in the parity and
// exact-copy checks even when the current source slice delegates their display.
const sharedVaultSurfaceLocaleKeys = new Set([
  ...editorModeLocaleKeys.map(key => `knowledge.${key}`),
  ...[
    'quickSwitcher', 'quickSwitcherDescription', 'alreadyOpen',
    'partialCatalogFailure', 'knowledgeCommands', 'semanticSearchFor',
    'semanticSearchResults', 'semanticUnavailable', 'previousTab', 'nextTab',
    'closeActiveTab', 'focusFiles', 'focusPane', 'focusLinks',
    'commandUnavailable', 'exactResults', 'indexedSearchResults', 'semanticSearch',
  ].map(key => `knowledge.${key}`),
  'knowledge.properties',
  'knowledge.tags',
  'knowledge.noProperties',
  'knowledge.noTags',
  'knowledge.outline',
])

describe('Read-only editor mode locale contracts', () => {
  it.each(Object.entries(resources))(
    '%s resolves every editor mode key directly',
    (code, resource) => {
      for (const key of editorModeLocaleKeys) {
        const qualifiedKey = `knowledge.${key}`
        const value = getTranslation(
          resource.translation as Record<string, unknown>,
          qualifiedKey,
        )

        expect(value, `${code} is missing ${qualifiedKey}`).toEqual(expect.any(String))
        expect((value as string).trim(), `${code} has an empty ${qualifiedKey}`)
          .not.toBe('')
      }
    },
  )

  it('keeps the exact English editor mode copy', () => {
    expect(enUS.knowledge).toMatchObject({
      source: 'Source',
      livePreview: 'Live Preview',
      emptyNote: 'This note is empty.',
      pageInvalid: 'The projected page data is invalid.',
      canonicalPathUnavailable: 'The canonical vault path is unavailable.',
      pagePreview: '{{title}} preview',
      previewUnavailable: 'Preview unavailable.',
      footnotes: 'Footnotes',
      sourceProvenance: 'Source provenance',
      lineEnding: 'Line ending',
      encoding: 'Encoding',
      contentHash: 'Content hash',
      readOnlyMode: '{{mode}} is read-only',
      headingLevel: 'Level {{level}} {{title}}',
    })
  })
})

const commandNavigationLocaleKeys = [
  'quickSwitcher', 'quickSwitcherDescription', 'alreadyOpen',
  'partialCatalogFailure', 'knowledgeCommands', 'semanticSearchFor',
  'semanticSearchResults', 'semanticUnavailable', 'previousTab', 'nextTab',
  'closeActiveTab', 'focusFiles', 'focusPane', 'focusLinks',
  'commandUnavailable', 'exactResults', 'indexedSearchResults', 'semanticSearch',
] as const

const knowledgeCommandLocaleKeys = [
  'viewReading', 'viewSource', 'viewLivePreview', 'viewGraph', 'splitRight',
  'splitDown', 'closePane', 'closeTab', 'previousTab', 'nextTab', 'scanVault',
  'focusFiles', 'focusPane', 'focusLinks', 'requiresActiveTab',
  'requiresActivePane', 'requiresMultiplePanes', 'requiresSelectedVault',
  'requiresFileTree', 'requiresLinks',
] as const

const rawEnglishRuntimeLeafAllowlist = new Set([
  'de-DE:commands.viewGraph',
  'fr-FR:commands.viewSource',
])

const approvedNonEnglishCommandNavigationCopy = {
  'bn-IN': ['দ্রুত সুইচার', 'সূচিবদ্ধ ভল্ট নোট খুলুন', 'খোলা', '{{count}}টি ভল্ট ক্যাটালগ লোড করা যায়নি', 'জ্ঞান কমান্ড', '{{query}}-এর জন্য অর্থভিত্তিক অনুসন্ধান', 'অর্থভিত্তিক ফলাফল', 'অর্থভিত্তিক অনুসন্ধানের জন্য এমবেডিং মডেল প্রয়োজন', 'পূর্ববর্তী ট্যাব', 'পরবর্তী ট্যাব', 'সক্রিয় ট্যাব বন্ধ করুন', 'ভল্ট ফাইলে ফোকাস করুন', 'সক্রিয় পেনে ফোকাস করুন', 'নোট লিঙ্কে ফোকাস করুন', 'কমান্ড অনুপলব্ধ'],
  'ca-ES': ['Selector ràpid', 'Obre una nota indexada de la volta', 'Oberta', "No s'han pogut carregar {{count}} catàlegs de volta", 'Ordres de coneixement', 'Cerca semàntica de {{query}}', 'Resultats semàntics', "La cerca semàntica requereix un model d'incrustacions", 'Pestanya anterior', 'Pestanya següent', 'Tanca la pestanya activa', 'Enfoca els fitxers de la volta', 'Enfoca el panell actiu', 'Enfoca els enllaços de la nota', 'Ordre no disponible'],
  'de-DE': ['Schnellwechsler', 'Indizierte Tresornotiz öffnen', 'Offen', '{{count}} Tresorkatalog konnte nicht geladen werden', 'Wissensbefehle', 'Semantische Suche nach {{query}}', 'Semantische Ergebnisse', 'Semantische Suche erfordert ein Einbettungsmodell', 'Vorheriger Tab', 'Nächster Tab', 'Aktiven Tab schließen', 'Tresordateien fokussieren', 'Aktiven Bereich fokussieren', 'Notizlinks fokussieren', 'Befehl nicht verfügbar'],
  'es-ES': ['Selector rápido', 'Abrir una nota indexada de la bóveda', 'Abierta', 'No se pudieron cargar {{count}} catálogos de bóveda', 'Comandos de conocimiento', 'Búsqueda semántica de {{query}}', 'Resultados semánticos', 'La búsqueda semántica requiere un modelo de incrustaciones', 'Pestaña anterior', 'Pestaña siguiente', 'Cerrar pestaña activa', 'Enfocar archivos de la bóveda', 'Enfocar panel activo', 'Enfocar enlaces de la nota', 'Comando no disponible'],
  'fr-FR': ['Sélecteur rapide', 'Ouvrir une note indexée du coffre', 'Ouverte', 'Impossible de charger {{count}} catalogues de coffre', 'Commandes de connaissances', 'Recherche sémantique de {{query}}', 'Résultats sémantiques', "La recherche sémantique nécessite un modèle d'embeddings", 'Onglet précédent', 'Onglet suivant', "Fermer l'onglet actif", 'Cibler les fichiers du coffre', 'Cibler le volet actif', 'Cibler les liens de la note', 'Commande indisponible'],
  'it-IT': ['Selettore rapido', 'Apri una nota indicizzata della cassaforte', 'Aperta', 'Impossibile caricare {{count}} cataloghi della cassaforte', 'Comandi della conoscenza', 'Ricerca semantica per {{query}}', 'Risultati semantici', 'La ricerca semantica richiede un modello di embedding', 'Scheda precedente', 'Scheda successiva', 'Chiudi scheda attiva', 'Attiva i file della cassaforte', 'Attiva il riquadro corrente', 'Attiva i link della nota', 'Comando non disponibile'],
  'ja-JP': ['クイックスイッチャー', 'インデックス済みの保管庫ノートを開く', '開いています', '{{count}} 件の保管庫カタログを読み込めませんでした', 'ナレッジコマンド', '{{query}} のセマンティック検索', 'セマンティック結果', 'セマンティック検索には埋め込みモデルが必要です', '前のタブ', '次のタブ', 'アクティブなタブを閉じる', '保管庫ファイルにフォーカス', 'アクティブなペインにフォーカス', 'ノートリンクにフォーカス', 'コマンドを使用できません'],
  'pl-PL': ['Szybki przełącznik', 'Otwórz zindeksowaną notatkę skarbca', 'Otwarta', 'Nie udało się załadować {{count}} katalogów skarbca', 'Polecenia wiedzy', 'Wyszukiwanie semantyczne: {{query}}', 'Wyniki semantyczne', 'Wyszukiwanie semantyczne wymaga modelu osadzania', 'Poprzednia karta', 'Następna karta', 'Zamknij aktywną kartę', 'Ustaw fokus na plikach skarbca', 'Ustaw fokus na aktywnym panelu', 'Ustaw fokus na linkach notatki', 'Polecenie niedostępne'],
  'pt-BR': ['Alternador rápido', 'Abrir uma nota indexada do cofre', 'Aberta', 'Não foi possível carregar {{count}} catálogos do cofre', 'Comandos de conhecimento', 'Pesquisa semântica por {{query}}', 'Resultados semânticos', 'A pesquisa semântica requer um modelo de embeddings', 'Guia anterior', 'Próxima guia', 'Fechar guia ativa', 'Focar arquivos do cofre', 'Focar painel ativo', 'Focar links da nota', 'Comando indisponível'],
  'ru-RU': ['Быстрый переключатель', 'Открыть проиндексированную заметку хранилища', 'Открыта', 'Не удалось загрузить {{count}} каталогов хранилища', 'Команды знаний', 'Семантический поиск: {{query}}', 'Семантические результаты', 'Для семантического поиска нужна модель эмбеддингов', 'Предыдущая вкладка', 'Следующая вкладка', 'Закрыть активную вкладку', 'Перейти к файлам хранилища', 'Перейти к активной панели', 'Перейти к ссылкам заметки', 'Команда недоступна'],
  'tr-TR': ['Hızlı değiştirici', 'Dizinlenmiş bir kasa notunu aç', 'Açık', '{{count}} kasa kataloğu yüklenemedi', 'Bilgi komutları', '{{query}} için anlamsal arama', 'Anlamsal sonuçlar', 'Anlamsal arama için bir gömme modeli gerekir', 'Önceki sekme', 'Sonraki sekme', 'Etkin sekmeyi kapat', 'Kasa dosyalarına odaklan', 'Etkin bölmeye odaklan', 'Not bağlantılarına odaklan', 'Komut kullanılamıyor'],
  'zh-CN': ['快速切换', '打开已索引的知识库笔记', '已打开', '无法加载 {{count}} 个知识库目录', '知识命令', '对 {{query}} 进行语义搜索', '语义结果', '语义搜索需要嵌入模型', '上一个标签页', '下一个标签页', '关闭当前标签页', '聚焦知识库文件', '聚焦当前窗格', '聚焦笔记链接', '命令不可用'],
  'zh-TW': ['快速切換', '開啟已索引的知識庫筆記', '已開啟', '無法載入 {{count}} 個知識庫目錄', '知識命令', '對 {{query}} 進行語意搜尋', '語意結果', '語意搜尋需要嵌入模型', '上一個分頁', '下一個分頁', '關閉目前分頁', '聚焦知識庫檔案', '聚焦目前窗格', '聚焦筆記連結', '命令無法使用'],
} as const

describe('Command-navigation locale contracts', () => {
  it.each(Object.entries(resources))('%s resolves all 38 command-navigation leaves directly', (code, resource) => {
    const translation = resource.translation as Record<string, unknown>
    for (const key of commandNavigationLocaleKeys) {
      const value = getTranslation(translation, `knowledge.${key}`)
      expect(value, `${code} is missing knowledge.${key}`).toEqual(expect.any(String))
      expect((value as string).trim()).not.toBe('')
    }
    for (const key of knowledgeCommandLocaleKeys) {
      const value = getTranslation(translation, `knowledge.commands.${key}`)
      expect(value, `${code} is missing knowledge.commands.${key}`).toEqual(expect.any(String))
      expect((value as string).trim()).not.toBe('')
    }
  })

  it('keeps exact English command-navigation copy', () => {
    expect(enUS.knowledge).toMatchObject({
      quickSwitcher: 'Quick switcher', quickSwitcherDescription: 'Open an indexed vault note',
      alreadyOpen: 'Open', partialCatalogFailure: '{{count}} vault catalog could not be loaded',
      knowledgeCommands: 'Knowledge commands', semanticSearchFor: 'Semantic search for {{query}}',
      semanticSearchResults: 'Semantic results', semanticUnavailable: 'Semantic search requires an embedding model',
      previousTab: 'Previous tab', nextTab: 'Next tab', closeActiveTab: 'Close active tab',
      focusFiles: 'Focus vault files', focusPane: 'Focus active pane', focusLinks: 'Focus note links',
      commandUnavailable: 'Command unavailable', exactResults: 'Exact matches',
      indexedSearchResults: 'Indexed results', semanticSearch: 'Semantic search',
      commands: {
        viewReading: 'Reading', viewSource: 'Source', viewLivePreview: 'Live Preview', viewGraph: 'Graph',
        splitRight: 'Split pane right', splitDown: 'Split pane down', closePane: 'Close pane',
        closeTab: 'Close active tab', previousTab: 'Previous tab', nextTab: 'Next tab', scanVault: 'Scan vault',
        focusFiles: 'Focus vault files', focusPane: 'Focus active pane', focusLinks: 'Focus note links',
        requiresActiveTab: 'Requires an active tab', requiresActivePane: 'Requires an active pane',
        requiresMultiplePanes: 'Requires multiple panes', requiresSelectedVault: 'Select a vault first',
        requiresFileTree: 'File tree unavailable', requiresLinks: 'Note links unavailable',
      },
    })
  })

  it.each(Object.entries(approvedNonEnglishCommandNavigationCopy))(
    '%s keeps the approved localized command-navigation copy',
    (code, approvedCopy) => {
      const translation = resources[code as keyof typeof resources]
        .translation as Record<string, unknown>
      for (const [index, key] of commandNavigationLocaleKeys.slice(0, 15).entries()) {
        expect(getTranslation(translation, `knowledge.${key}`)).toBe(approvedCopy[index])
      }
    },
  )

  it.each(Object.entries(resources).filter(([code]) => code !== 'en-US'))(
    '%s has no unapproved raw-English runtime leaves',
    (code, resource) => {
      const translation = resource.translation as Record<string, unknown>
      const english = enUS as unknown as { knowledge: Record<string, unknown> }
      for (const key of ['exactResults', 'indexedSearchResults', 'semanticSearch'] as const) {
        expect(getTranslation(translation, `knowledge.${key}`)).not.toBe(english.knowledge[key])
      }
      for (const key of knowledgeCommandLocaleKeys) {
        if (rawEnglishRuntimeLeafAllowlist.has(`${code}:commands.${key}`)) continue
        expect(getTranslation(translation, `knowledge.commands.${key}`)).not.toBe(
          getTranslation(english.knowledge, `commands.${key}`),
        )
      }
    },
  )

  it.each(Object.entries(resources))('%s preserves command-navigation interpolation tokens', (code, resource) => {
    const translation = resource.translation as Record<string, unknown>
    expect(getTranslation(translation, 'knowledge.partialCatalogFailure')).toContain('{{count}}')
    expect(getTranslation(translation, 'knowledge.semanticSearchFor')).toContain('{{query}}')
  })
})

describe('Unused Key Detection', () => {
  it(
    'all en-US leaf keys should be referenced in source files',
    () => {
      const srcDir = path.resolve(__dirname, '../../..')
      const localesDir = path.resolve(__dirname)
      const ignoredDirs = new Set(['.next', 'node_modules', 'coverage', 'dist', 'build'])

      const collectFiles = (dir: string): string[] => {
        let entries: fs.Dirent[]
        try {
          entries = fs.readdirSync(dir, { withFileTypes: true })
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []
          throw error
        }

        return entries.flatMap(entry => {
          const full = path.join(dir, entry.name)
          if (entry.isDirectory()) {
            if (ignoredDirs.has(entry.name)) return []
            return collectFiles(full)
          }
          return [path.relative(srcDir, full)]
        })
      }

      const files = collectFiles(srcDir)
      const sourceFiles = files.filter(f => {
        const full = path.join(srcDir, f)
        if (full.startsWith(localesDir)) return false
        if (f.endsWith('.test.ts') || f.endsWith('.test.tsx')) return false
        return f.endsWith('.ts') || f.endsWith('.tsx')
      })

      // Normalize optional chaining (t?.common?.key → t.common.key)
      // so that keys like "common.errorDetails" match "common?.errorDetails"
      const corpus = sourceFiles
        .map(f => {
          try {
            return fs.readFileSync(path.join(srcDir, f), 'utf-8')
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code === 'ENOENT') return ''
            throw error
          }
        })
        .join('\n')
        .replace(/\?\./g, '.')

      const leafKeys = getKeys(enUS)
      const unused = leafKeys.filter(
        key => !corpus.includes(key) && !sharedVaultSurfaceLocaleKeys.has(key),
      )

      expect(
        unused,
        `Found ${unused.length} unused i18n key(s):\n${unused.join('\n')}`,
      ).toEqual([])
    },
    // v0.7.31 — bumped from 30s to 120s. The test walks every .ts/.tsx
    // file in src/ and string-matches every en-US leaf key against the
    // corpus. As the codebase has grown (Dashboard, podcast presets,
    // auto-fill, etc.), the file walk has crept past 30s on slower
    // boxes (especially under cold-cache CI). 120s gives comfortable
    // headroom; the check is still well under 1 min on a warm-cache
    // local run.
    120_000,
  )
})

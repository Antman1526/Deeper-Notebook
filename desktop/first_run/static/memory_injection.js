// Injected into the main UI to add a "Memory" link to upstream's Settings page,
// and to surface a one-time OpenChronicle install reminder when applicable.
(function () {
  if (window.__DEEPER_NOTEBOOK_MEMORY_INJECTED) return;
  window.__DEEPER_NOTEBOOK_MEMORY_INJECTED = true;

  // v0.8.130 — a rail link like the app's own, with a drawn icon and a translated
  // label. It was a bordered box with an emoji, and it was found through the English
  // aria-label "Settings", so it never appeared in any other language.
  var MEMORY_LABELS = {"en": "Memory", "de": "Gedächtnis", "es": "Memoria", "ca": "Memòria", "fr": "Mémoire", "it": "Memoria", "pt": "Memória", "pl": "Pamięć", "ru": "Память", "tr": "Bellek", "ja": "メモリ", "zh-CN": "记忆", "zh-TW": "記憶", "bn": "মেমরি"};
  var MEMORY_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5a3 3 0 1 0-6 .1 4 4 0 0 0-2.5 5.8A4 4 0 0 0 4.6 17 4 4 0 0 0 12 18z"/><path d="M12 5a3 3 0 1 1 6 .1 4 4 0 0 1 2.5 5.8 4 4 0 0 1-1.1 6.1A4 4 0 0 1 12 18z"/><path d="M12 5v13"/></svg>';

  function memoryLabel() {
    var lang = document.documentElement.lang || 'en';
    return MEMORY_LABELS[lang] || MEMORY_LABELS[lang.split('-')[0]] || MEMORY_LABELS.en;
  }

  function injectMemoryLink() {
    var existing = document.querySelector('.onp-memory-link');
    if (existing) {
      // The interface language can change while the app is open.
      var label = existing.querySelector('span');
      if (label && label.textContent !== memoryLabel()) label.textContent = memoryLabel();
      return;
    }
    var settingsLink = document.querySelector('#dn-rail a.dn-rail-link[href="/settings"]');
    var settingsContainer = (settingsLink && settingsLink.closest('ul')) || document.querySelector(
      '[data-page="settings"], [aria-label*="Settings"]'
    );
    if (!settingsContainer) return;
    const link = document.createElement('a');
    link.className = 'dn-rail-link onp-memory-link';
    link.href = (
      window.DEEPER_NOTEBOOK_MEMORY_URL || window.ONP_MEMORY_URL || '#'
    );
    link.innerHTML = MEMORY_ICON;
    var text = document.createElement('span');
    text.textContent = memoryLabel();
    link.appendChild(text);
    link.target = '_blank';
    var item = document.createElement(settingsContainer.tagName === 'UL' ? 'li' : 'div');
    item.appendChild(link);
    settingsContainer.appendChild(item);
  }
  const observer = new MutationObserver(injectMemoryLink);
  observer.observe(document.body, { childList: true, subtree: true });
  injectMemoryLink();

  const remindOpenChronicle = (
    window.DEEPER_NOTEBOOK_REMIND_OPENCHRONICLE
    ?? window.ONP_REMIND_OPENCHRONICLE
    ?? false
  );
  if (remindOpenChronicle) {
    if (window.showToast) {
      window.showToast(
        'OpenChronicle not detected. Install for ambient memory →',
        {
          variant: 'info', autoDismissMs: null,
          actionLabel: 'Open install page',
          onAction: () => window.open(
            'https://github.com/Einsia/OpenChronicle/releases/latest', '_blank'),
          onClose: () => fetch(
            '/api/config/dismiss_openchronicle_reminder', {method: 'POST'}
          ).catch(() => {}),
        }
      );
    }
  }
})();

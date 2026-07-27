// Injected into the main UI to add a "Memory" link to upstream's Settings page,
// and to surface a one-time OpenChronicle install reminder when applicable.
(function () {
  if (window.__DEEPER_NOTEBOOK_MEMORY_INJECTED) return;
  window.__DEEPER_NOTEBOOK_MEMORY_INJECTED = true;

  function injectMemoryLink() {
    const settingsContainer = document.querySelector(
      '[data-page="settings"], [aria-label*="Settings"]'
    );
    if (!settingsContainer || settingsContainer.querySelector('.onp-memory-link')) return;
    const link = document.createElement('a');
    link.className = 'onp-memory-link';
    link.href = (window.DEEPER_NOTEBOOK_MEMORY_URL || '#');
    link.textContent = '🧠 Memory';
    link.target = '_blank';
    Object.assign(link.style, {
      display: 'block', padding: '8px 12px', marginTop: '12px',
      borderRadius: '6px', textDecoration: 'none',
      color: 'var(--primary, #2D7FF9)', border: '1px solid var(--border, #ccc)',
    });
    settingsContainer.appendChild(link);
  }
  const observer = new MutationObserver(injectMemoryLink);
  observer.observe(document.body, { childList: true, subtree: true });
  injectMemoryLink();

  if (window.DEEPER_NOTEBOOK_REMIND_OPENCHRONICLE) {
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

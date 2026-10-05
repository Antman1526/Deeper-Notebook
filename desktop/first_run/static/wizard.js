(() => {
  const THEMES = window.DN_THEME_CATALOG;
  const dnWizardT = window.dnWizardT;

  // v0.8.130 — fixed sentences the launcher/server send as `message` / `error`,
  // keyed by the exact English literal. Only literals with no interpolated
  // values belong here; paths, exception text and URLs are shown as received.
  // desktop/tests/test_wizard_i18n.py asserts each literal still appears
  // verbatim in the backend source, so a reworded sentence fails a test
  // instead of silently falling back to English.
  const FIXED_MESSAGE_KEYS = {
    // desktop/app.py
    'Launcher starting…': 'msg.launcherStarting',
    'Main window opening…': 'msg.windowOpening',
    // desktop/launcher.py
    'Local resource governor deferred spawn': 'msg.governorDeferred',
    'sidecar failed its post-spawn health check': 'msg.healthCheckFailed',
  };
  // desktop/first_run/server.py, /api/save handler
  const SAVE_ERROR_KEYS = {
    'invalid provider': 'error.invalidProvider',
  };
  const fromTable = (table, text) =>
    Object.prototype.hasOwnProperty.call(table, text) ? dnWizardT(table[text]) : text;

  // Progress step codes ("supervisor.surreal") get a friendly label when the
  // dictionary has a `step.<code>` key, else the raw code as before.
  const stepLabel = (code) => {
    const key = 'step.' + code;
    const label = dnWizardT(key);
    return label !== key ? label : code.replaceAll('.', ' › ');
  };

  // v0.8.130 — indigo is the one brand; the wizard used to preselect teal Research Core Dark.
  let chosenTheme = 'gemini-forward-light';
  let openchronicleChoice = 'skip';
  const html = document.documentElement;

  // v0.8.130 — translate the static markup once at startup. English stays in
  // index.html as the no-JS fallback; en-US re-applies the same text.
  // data-i18n-html values are authored by us (never user input), so innerHTML is safe.
  const applyI18n = () => {
    html.lang = window.dnWizardLocale();
    document.querySelectorAll('[data-i18n]').forEach(el => {
      el.textContent = dnWizardT(el.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
      el.innerHTML = dnWizardT(el.dataset.i18nHtml);
    });
    document.querySelectorAll('[data-i18n-attr]').forEach(el => {
      el.dataset.i18nAttr.split(',').forEach(pair => {
        const [attr, key] = pair.split(':').map(part => part.trim());
        if (attr && key) el.setAttribute(attr, dnWizardT(key));
      });
    });
  };
  applyI18n();

  const screens = document.querySelectorAll('[data-screen]');
  const show = (name) => screens.forEach(s =>
    s.hidden = s.dataset.screen !== name);

  const setTheme = (id) => {
    chosenTheme = id;
    html.dataset.theme = id;
    document.querySelectorAll('.theme-card').forEach(c => {
      c.classList.toggle('selected', c.dataset.theme === id);
    });
  };

  // Build theme grid
  const grid = document.getElementById('theme_grid');
  THEMES.forEach(theme => {
    const card = document.createElement('div');
    card.className = 'theme-card';
    card.dataset.theme = theme.id;
    card.innerHTML = `
      <div class="theme-swatch" style="--swatch-bg:${theme.bg};--swatch-fg:${theme.fg}"></div>
      <div class="theme-name"></div>
    `;
    // v0.8.130 — only the six generic names (Dark, Paper, System…) are
    // translated; proper-noun themes keep their catalog name. dnWizardT
    // returns the key itself when it has no entry, which is the "no key" test.
    const themeKey = 'theme.' + theme.id;
    const translated = dnWizardT(themeKey);
    card.querySelector('.theme-name').textContent =
      translated !== themeKey ? translated : theme.name;
    card.addEventListener('click', () => setTheme(theme.id));
    grid.appendChild(card);
  });
  setTheme(chosenTheme);

  // Dark-mode quick toggle: flips between the Research Core defaults.
  document.getElementById('dark_toggle').addEventListener('click', () => {
    const selectedTheme = THEMES.find(theme => theme.id === chosenTheme);
    setTheme(selectedTheme && selectedTheme.dark
      ? 'research-core-light'
      : 'gemini-forward-light');
  });

  // Pre-fill model dir
  const modelDirInput = document.getElementById('model_dir');
  modelDirInput.value = navigator.platform.toLowerCase().includes('win')
    ? '%USERPROFILE%\\Desktop\\AI_Models'
    : '~/Desktop/AI_Models';

  document.querySelectorAll('button[data-next], button[data-back]').forEach(btn => {
    btn.addEventListener('click', async () => {
      // Screen-5.5 OpenChronicle choices: capture before navigating away.
      const action = btn.dataset.onclick;
      if (action === 'open_openchronicle_install') {
        openchronicleChoice = 'prompt';
        // PyWebView's WKWebView handling of `window.open(url, '_blank')` is
        // unreliable on macOS — can navigate the wizard window itself or
        // crash the WebView. Route through the aiohttp server, which uses
        // Python's `webbrowser.open()` (the OS handler, never the WebView).
        fetch('/api/open-url', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            url: 'https://github.com/Einsia/OpenChronicle/releases/latest',
          }),
        }).catch(() => { /* swallow — opening the page is best-effort */ });
      } else if (action === 'skip_openchronicle') {
        openchronicleChoice = 'skip';
      }
      const target = btn.dataset.next || btn.dataset.back;
      if (target === 'done') {
        const choice = document.querySelector('input[name=choice]:checked').value;
        // Send raw model_dir; the server expands ~ and %USERPROFILE% because
        // the browser cannot see the user's HOME / USERPROFILE env vars.
        const payload = {
          model_dir: modelDirInput.value,
          provider: choice,
          default_model: document.getElementById('default_model').value || '',
          theme: chosenTheme,
          openchronicle_choice: openchronicleChoice,
        };
        show('setting-up');
        const list = document.getElementById('progress-list');
        const latest = document.getElementById('progress-latest');
        const elapsed = document.getElementById('progress-elapsed');
        const startTs = Date.now();
        elapsed.textContent = dnWizardT('progress.seconds', {n: 0});
        setInterval(() => {
          elapsed.textContent = dnWizardT('progress.seconds', {n: Math.round((Date.now() - startTs) / 1000)});
        }, 500);

        // Save config first
        // v0.5.10 — retry-aware save. Previously a 500 here showed
        // "Failed to save config." and the wizard was stuck. Now we surface
        // the actual error from the response body + offer a retry button.
        const attemptSave = async () => {
          const resp = await fetch('/api/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
          });
          if (!resp.ok) {
            let detail = `HTTP ${resp.status}`;
            try {
              const body = await resp.json();
              if (body.error) detail = fromTable(SAVE_ERROR_KEYS, body.error);
              else if (body.detail) detail = fromTable(SAVE_ERROR_KEYS, body.detail);
            } catch (_) { /* not JSON */ }
            throw new Error(detail);
          }
          return resp;
        };

        try {
          await attemptSave();
        } catch (err) {
          latest.textContent = dnWizardT('progress.saveFailed', {message: err.message});
          const retryBtn = document.createElement('button');
          retryBtn.textContent = dnWizardT('common.retry');
          retryBtn.className = 'primary';
          retryBtn.style.marginTop = '12px';
          retryBtn.addEventListener('click', async () => {
            latest.textContent = dnWizardT('progress.retrying');
            retryBtn.remove();
            try {
              await attemptSave();
              latest.textContent = dnWizardT('progress.starting');
              // Continue with the progress stream below
            } catch (err2) {
              latest.textContent = dnWizardT('progress.retryFailed', {message: err2.message});
              latest.parentElement.appendChild(retryBtn);
            }
          });
          latest.parentElement.appendChild(retryBtn);
          return;
        }

        // Then subscribe to progress
        const es = new EventSource('/api/progress');
        const items = {};
        es.onmessage = (ev) => {
          const evt = JSON.parse(ev.data);
          let li = items[evt.step];
          if (!li) {
            li = document.createElement('li');
            li.textContent = stepLabel(evt.step);
            list.appendChild(li);
            items[evt.step] = li;
          }
          li.dataset.status = evt.status;
          // v0.8.130 — fixed launcher sentences are translated by exact match;
          // every other message is free-form backend text and shown as received.
          if (evt.message) latest.textContent = fromTable(FIXED_MESSAGE_KEYS, evt.message);
          if (evt.step === 'ready' && evt.status === 'done') {
            es.close();
          }
        };
        es.onerror = () => {
          latest.textContent = dnWizardT('progress.disconnected');
        };
      } else {
        show(target);
      }
    });
  });

  show('welcome');
})();

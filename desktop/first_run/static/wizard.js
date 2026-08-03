(() => {
  const THEMES = window.DN_THEME_CATALOG;

  let chosenTheme = 'research-core-dark';
  let openchronicleChoice = 'skip';
  const html = document.documentElement;

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
  THEMES.forEach(t => {
    const card = document.createElement('div');
    card.className = 'theme-card';
    card.dataset.theme = t.id;
    card.innerHTML = `
      <div class="theme-swatch" style="--swatch-bg:${t.bg};--swatch-fg:${t.fg}"></div>
      <div class="theme-name">${t.name}</div>
    `;
    card.addEventListener('click', () => setTheme(t.id));
    grid.appendChild(card);
  });
  setTheme(chosenTheme);

  // Dark-mode quick toggle: flips between the Research Core defaults.
  document.getElementById('dark_toggle').addEventListener('click', () => {
    const selectedTheme = THEMES.find(theme => theme.id === chosenTheme);
    setTheme(selectedTheme && selectedTheme.dark
      ? 'research-core-light'
      : 'research-core-dark');
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
        setInterval(() => {
          elapsed.textContent = Math.round((Date.now() - startTs) / 1000) + 's';
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
              if (body.error) detail = body.error;
              else if (body.detail) detail = body.detail;
            } catch (_) { /* not JSON */ }
            throw new Error(detail);
          }
          return resp;
        };

        try {
          await attemptSave();
        } catch (err) {
          latest.textContent = `Failed to save config: ${err.message}`;
          const retryBtn = document.createElement('button');
          retryBtn.textContent = 'Retry';
          retryBtn.className = 'primary';
          retryBtn.style.marginTop = '12px';
          retryBtn.addEventListener('click', async () => {
            latest.textContent = 'Retrying…';
            retryBtn.remove();
            try {
              await attemptSave();
              latest.textContent = 'starting…';
              // Continue with the progress stream below
            } catch (err2) {
              latest.textContent = `Failed again: ${err2.message}`;
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
            li.textContent = evt.step.replaceAll('.', ' › ');
            list.appendChild(li);
            items[evt.step] = li;
          }
          li.dataset.status = evt.status;
          if (evt.message) latest.textContent = evt.message;
          if (evt.step === 'ready' && evt.status === 'done') {
            es.close();
          }
        };
        es.onerror = () => {
          latest.textContent = '(progress stream disconnected)';
        };
      } else {
        show(target);
      }
    });
  });

  show('welcome');
})();

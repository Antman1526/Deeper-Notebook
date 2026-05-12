(() => {
  const THEMES = [
    { id: 'light-blue', name: 'Light Blue', bg: '#FFFFFF', fg: '#2D7FF9' },
    { id: 'system', name: 'System', bg: '#FFFFFF', fg: '#1A2B3C' },
    { id: 'solarized-light', name: 'Solarized Light', bg: '#FDF6E3', fg: '#268BD2' },
    { id: 'github-light', name: 'GitHub Light', bg: '#FFFFFF', fg: '#0969DA' },
    { id: 'paper', name: 'Paper', bg: '#FBF8F1', fg: '#8B5A2B' },
    { id: 'dark', name: 'Dark', bg: '#0F1419', fg: '#5AB1FF' },
    { id: 'solarized-dark', name: 'Solarized Dark', bg: '#002B36', fg: '#268BD2' },
    { id: 'dracula', name: 'Dracula', bg: '#282A36', fg: '#BD93F9' },
    { id: 'nord', name: 'Nord', bg: '#2E3440', fg: '#88C0D0' },
  ];

  let chosenTheme = 'light-blue';
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
  setTheme('light-blue');

  // Dark-mode quick toggle: flips light-blue <-> dark
  document.getElementById('dark_toggle').addEventListener('click', () => {
    const dark = ['dark', 'solarized-dark', 'dracula', 'nord'].includes(chosenTheme);
    setTheme(dark ? 'light-blue' : 'dark');
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
        try {
          window.open('https://github.com/Einsia/OpenChronicle/releases/latest', '_blank');
        } catch (e) { /* sandboxed contexts may block window.open — non-fatal */ }
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
        const saveResp = await fetch('/api/save', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload),
        });
        if (!saveResp.ok) {
          latest.textContent = 'Failed to save config.';
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

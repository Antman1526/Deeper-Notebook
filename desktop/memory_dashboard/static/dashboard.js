(async () => {
  // Apply theme from /api/theme
  try {
    const t = await fetch('/api/theme').then(r => r.json());
    document.documentElement.dataset.theme = t.theme || 'light-blue';
  } catch (e) {
    document.documentElement.dataset.theme = 'light-blue';
  }

  async function loadList(kind, listId, countId) {
    try {
      const r = await fetch(`/api/memory/${kind}s`);
      const data = await r.json();
      const records = data.records || [];
      document.getElementById(countId).textContent = records.length;
      const list = document.getElementById(listId);
      list.innerHTML = '';
      records.forEach(rec => {
        const li = document.createElement('li');
        // Build with DOM APIs + textContent — memory text may contain arbitrary
        // user-derived content (chat messages, file paths, code snippets), so
        // string-interpolating into innerHTML would be an XSS vector.
        const textSpan = document.createElement('span');
        textSpan.style.flex = '1';
        textSpan.textContent = rec.text || rec.summary || '(no text)';

        const confSpan = document.createElement('span');
        confSpan.style.color = '#888';
        const confNum = typeof rec.confidence === 'number' ? rec.confidence : 0;
        confSpan.textContent = confNum.toFixed(2);

        const btn = document.createElement('button');
        btn.dataset.kind = kind;
        btn.dataset.id = (rec.id || '').replace(/^[^:]+:/, '');
        btn.textContent = 'Forget';
        btn.addEventListener('click', async (e) => {
          if (!confirm('Forget this record?')) return;
          await fetch(`/api/memory/${kind}/${e.target.dataset.id}`, {method: 'DELETE'});
          loadList(kind, listId, countId);
        });

        li.appendChild(textSpan);
        li.appendChild(confSpan);
        li.appendChild(btn);
        list.appendChild(li);
      });
    } catch (e) {
      console.error('loadList failed', kind, e);
    }
  }

  await loadList('preference', 'pref-list', 'pref-count');
  await loadList('fact', 'fact-list', 'fact-count');
  await loadList('episode', 'ep-list', 'ep-count');

  // Ambient status
  try {
    const s = await fetch('/api/memory/ambient/status').then(r => r.json());
    const el = document.getElementById('ambient-status');
    el.textContent = s.available
      ? (s.paused ? 'Available — currently paused' : 'Active')
      : 'Not detected — install OpenChronicle to enable';
    document.getElementById('ambient-pause').addEventListener('click', async () => {
      await fetch('/api/memory/ambient/pause', {method: 'POST'});
      el.textContent = 'Available — currently paused';
    });
  } catch (e) {
    document.getElementById('ambient-status').textContent = '(error reading status)';
  }
})();

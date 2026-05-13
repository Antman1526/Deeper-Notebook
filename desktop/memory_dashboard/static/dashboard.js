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

  // ONP v0.5 — Capture Inbox
  // The inbox shows OpenChronicle screen events from the last N minutes so
  // the user can curate BEFORE they commit to memory. Dismissed events are
  // session-local (no backend mute) — re-open the window and they reappear.
  const dismissed = new Set();

  // P1-HIGH-05 — also track the latest ts seen so we can persist it on
  // approve / dismiss / mark-all and the server-side last_seen filter kicks in.
  let mostRecentTs = '';

  async function loadInbox() {
    const list = document.getElementById('inbox-list');
    const empty = document.getElementById('inbox-empty');
    const countEl = document.getElementById('inbox-count');
    const markAllBtn = document.getElementById('inbox-mark-all');
    if (!list) return;
    list.innerHTML = '';
    empty.hidden = true;
    if (markAllBtn) markAllBtn.hidden = true;

    let payload;
    try {
      payload = await fetch('/api/capture/inbox?minutes=30').then(r => r.json());
    } catch (e) {
      empty.hidden = false;
      empty.textContent = '(could not reach OpenChronicle bridge)';
      countEl.textContent = '0';
      return;
    }

    if (!payload.available) {
      empty.hidden = false;
      countEl.textContent = '0';
      return;
    }

    const events = (payload.events || []).filter(
      ev => !dismissed.has(eventId(ev))
    );
    countEl.textContent = String(events.length);
    // Track the newest event ts for the mark-seen watermark
    mostRecentTs = events.reduce((max, ev) => {
      const t = ev.ts || '';
      return t > max ? t : max;
    }, '');

    if (events.length === 0) {
      empty.hidden = false;
      empty.textContent = 'No new captures in the last 30 minutes.';
      return;
    }

    if (markAllBtn) markAllBtn.hidden = false;
    events.forEach(ev => list.appendChild(renderInboxRow(ev)));
  }

  async function markAllSeen() {
    if (!mostRecentTs) return;
    try {
      await fetch('/api/capture/mark_seen', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ts: mostRecentTs}),
      });
      await loadInbox();
    } catch (e) {
      // non-fatal
    }
  }

  function eventId(ev) {
    return ev.id || ev.ts || (ev.title || '') + (ev.app || '');
  }

  function renderInboxRow(ev) {
    const li = document.createElement('li');
    const row = document.createElement('div');
    row.className = 'inbox-event';

    const titleEl = document.createElement('span');
    titleEl.className = 'title';
    titleEl.textContent = ev.title || '(no title)';

    const metaEl = document.createElement('span');
    metaEl.className = 'meta';
    const parts = [];
    if (ev.app) parts.push(ev.app);
    if (ev.ts) parts.push(new Date(ev.ts).toLocaleTimeString());
    metaEl.textContent = parts.join(' • ');

    row.appendChild(titleEl);
    row.appendChild(metaEl);

    const actions = document.createElement('div');
    actions.className = 'inbox-actions';

    // P1-MED-09 audit fix: dropdown for kind so user can save as
    // fact / preference / episode (was hardcoded to 'fact' only).
    const kindSelect = document.createElement('select');
    kindSelect.className = 'btn-approve';
    kindSelect.setAttribute('aria-label', 'Save as kind');
    for (const k of ['fact', 'preference', 'episode']) {
      const opt = document.createElement('option');
      opt.value = k;
      opt.textContent = `Save as ${k}`;
      kindSelect.appendChild(opt);
    }
    // Default to fact, but make sure changing the dropdown alone doesn't fire
    // a save — user has to click the Save button next to it.
    const approveBtn = document.createElement('button');
    approveBtn.className = 'btn-approve';
    approveBtn.textContent = 'Save';
    approveBtn.addEventListener('click', async () => {
      approveBtn.disabled = true;
      kindSelect.disabled = true;
      const oldText = approveBtn.textContent;
      approveBtn.textContent = 'Saving…';
      try {
        const kind = kindSelect.value;
        const resp = await fetch('/api/memory/capture/approve', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            text: ev.title || '',
            source_app: ev.app || '',
            event_id: eventId(ev),
            ts: ev.ts || '',
            kind: kind,
          }),
        });
        if (!resp.ok) throw new Error('save failed');
        dismissed.add(eventId(ev));
        loadInbox();
        // Refresh the matching list at the bottom of the dashboard so the
        // newly-saved record shows up immediately.
        const listMap = {
          fact: ['fact', 'fact-list', 'fact-count'],
          preference: ['preference', 'pref-list', 'pref-count'],
          episode: ['episode', 'ep-list', 'ep-count'],
        };
        const args = listMap[kind];
        if (args) await loadList(...args);
      } catch (e) {
        approveBtn.disabled = false;
        kindSelect.disabled = false;
        approveBtn.textContent = oldText;
        approveBtn.title = 'Save failed — click to retry';
      }
    });

    const dismissBtn = document.createElement('button');
    dismissBtn.className = 'btn-dismiss';
    dismissBtn.textContent = 'Dismiss';
    dismissBtn.addEventListener('click', () => {
      dismissed.add(eventId(ev));
      loadInbox();
    });

    actions.appendChild(kindSelect);
    actions.appendChild(approveBtn);
    actions.appendChild(dismissBtn);
    row.appendChild(actions);

    li.appendChild(row);
    return li;
  }

  // Wire up the "Mark all as seen" button (button is hidden until inbox has
  // events). Click → POST /api/capture/mark_seen with the newest ts seen.
  const markAllBtn = document.getElementById('inbox-mark-all');
  if (markAllBtn) markAllBtn.addEventListener('click', markAllSeen);

  // ONP v0.5.4 — Active models panel: shows which model is in each role
  async function loadActiveModels() {
    const section = document.getElementById('active-models-section');
    const list = document.getElementById('active-models-list');
    if (!section || !list) return;
    let payload;
    try {
      payload = await fetch('/api/dashboard/active-models').then(r => r.json());
    } catch (e) {
      return;  // silently skip — section stays hidden
    }
    if (!payload.available || !payload.slots) return;
    list.innerHTML = '';
    // Render in fixed order so the layout doesn't shuffle
    const order = ['Chat', 'Tools', 'Reasoning', 'Transformation',
                   'Large Context', 'Embedding', 'Text-to-Speech', 'Speech-to-Text'];
    let anyAssigned = false;
    for (const label of order) {
      if (!(label in payload.slots)) continue;
      const dt = document.createElement('dt');
      dt.textContent = label;
      const dd = document.createElement('dd');
      const v = payload.slots[label];
      if (v) {
        dd.textContent = v;
        anyAssigned = true;
      } else {
        dd.textContent = '(not set)';
        dd.className = 'empty-slot';
      }
      list.appendChild(dt);
      list.appendChild(dd);
    }
    if (anyAssigned) section.hidden = false;
  }

  // ONP v0.5.5 — subtitle: "X facts · Y preferences · Z episodes"
  // Counts pulled from the same lists the sections render, so the header
  // stays in sync after Forget / Save-from-inbox actions.
  const counts = {fact: 0, preference: 0, episode: 0};
  function updateSubtitle() {
    const el = document.getElementById('memory-subtitle');
    if (!el) return;
    const parts = [];
    if (counts.fact)       parts.push(`${counts.fact} fact${counts.fact === 1 ? '' : 's'}`);
    if (counts.preference) parts.push(`${counts.preference} preference${counts.preference === 1 ? '' : 's'}`);
    if (counts.episode)    parts.push(`${counts.episode} episode${counts.episode === 1 ? '' : 's'}`);
    el.textContent = parts.length ? parts.join(' · ') : 'No memories yet';
  }
  // Patch the existing loadList to also update counts
  const _origLoadList = loadList;
  loadList = async function(kind, listId, countId) {
    const before = parseInt(document.getElementById(countId)?.textContent || '0', 10);
    await _origLoadList(kind, listId, countId);
    const after = parseInt(document.getElementById(countId)?.textContent || '0', 10);
    counts[kind] = after;
    updateSubtitle();
  };

  // ONP v0.5.5 — search bar. Wraps existing /api/memory/search shim
  // endpoint; debounced to avoid hammering on every keystroke.
  const searchInput = document.getElementById('memory-search');
  const searchClear = document.getElementById('memory-search-clear');
  const searchResultsSection = document.getElementById('search-results-section');
  const searchList = document.getElementById('search-list');
  const searchCount = document.getElementById('search-count');
  let searchDebounce = null;

  async function runSearch(q) {
    if (!q.trim()) {
      searchResultsSection.hidden = true;
      return;
    }
    searchResultsSection.hidden = false;
    searchList.innerHTML = '<li class="empty-state">Searching…</li>';
    try {
      const r = await fetch(`/api/memory/search?q=${encodeURIComponent(q)}`);
      const body = await r.json();
      const records = body.records || [];
      searchCount.textContent = String(records.length);
      searchList.innerHTML = '';
      if (records.length === 0) {
        const li = document.createElement('li');
        li.className = 'empty-state';
        li.textContent = `No matches for "${q}"`;
        searchList.appendChild(li);
        return;
      }
      for (const rec of records) {
        const li = document.createElement('li');
        const text = document.createElement('span');
        text.style.flex = '1';
        text.textContent = rec.text || rec.summary || rec.payload?.text || '(no text)';
        const meta = document.createElement('span');
        meta.style.color = 'var(--muted, #888)';
        meta.style.fontSize = '12px';
        const kind = rec.payload?.kind || rec.metadata?.kind || '?';
        const score = typeof rec.score === 'number' ? rec.score.toFixed(2) : '';
        meta.textContent = `${kind}${score ? ` · ${score}` : ''}`;
        li.appendChild(text);
        li.appendChild(meta);
        searchList.appendChild(li);
      }
    } catch (e) {
      searchList.innerHTML = `<li class="empty-state">Search failed: ${e.message}</li>`;
    }
  }

  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const q = e.target.value;
      searchClear.hidden = !q;
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => runSearch(q), 220);
    });
    searchClear.addEventListener('click', () => {
      searchInput.value = '';
      searchClear.hidden = true;
      searchResultsSection.hidden = true;
      searchInput.focus();
    });
  }

  await loadActiveModels();
  await loadInbox();
  await loadList('preference', 'pref-list', 'pref-count');
  await loadList('fact', 'fact-list', 'fact-count');
  await loadList('episode', 'ep-list', 'ep-count');
})();

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

  await loadInbox();
  await loadList('preference', 'pref-list', 'pref-count');
  await loadList('fact', 'fact-list', 'fact-count');
  await loadList('episode', 'ep-list', 'ep-count');
})();

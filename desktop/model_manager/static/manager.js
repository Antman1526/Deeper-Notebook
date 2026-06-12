(async () => {
  async function refresh() {
    const r = await fetch('/api/installed');
    const data = await r.json();
    const list = document.getElementById('installed-list');
    list.innerHTML = '';
    let total = 0;
    data.models.forEach(m => {
      total += m.size_mb;
      const li = document.createElement('li');
      li.innerHTML = `
        <span style="flex:1">${m.name}</span>
        <span class="cat">${m.class}</span>
        <span style="color:#888">${m.size_mb} MB</span>
        <button class="danger" data-rel="${m.rel}">Delete</button>
      `;
      li.querySelector('button').addEventListener('click', async (e) => {
        if (!confirm(`Delete ${m.name}?`)) return;
        await fetch('/api/installed/' + encodeURIComponent(m.rel), { method: 'DELETE' });
        refresh();
      });
      list.appendChild(li);
    });
    document.getElementById('disk-used').textContent = total + ' MB';
  }

  async function renderCatalog() {
    const r = await fetch('/api/catalog');
    const cat = await r.json();
    const root = document.getElementById('catalog');
    root.innerHTML = '';
    Object.entries(cat).forEach(([category, items]) => {
      const h3 = document.createElement('h3');
      h3.textContent = category.toUpperCase();
      h3.style.marginTop = '12px';
      root.appendChild(h3);
      items.forEach(item => {
        const div = document.createElement('div');
        div.innerHTML = `
          <strong>${item.name}</strong>
          <span style="color:#888">(${item.size_mb} MB)</span>
        `;
        root.appendChild(div);
      });
    });
  }

  await refresh();
  await renderCatalog();
})();

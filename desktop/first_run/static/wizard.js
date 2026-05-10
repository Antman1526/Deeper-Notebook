(() => {
  const screens = document.querySelectorAll('[data-screen]');
  const show = (name) => screens.forEach(s =>
    s.hidden = s.dataset.screen !== name);

  const modelDirInput = document.getElementById('model_dir');
  modelDirInput.value = navigator.platform.toLowerCase().includes('win')
    ? '%USERPROFILE%\\Desktop\\AI_Models'
    : '~/Desktop/AI_Models';

  document.querySelectorAll('button[data-next], button[data-back]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const target = btn.dataset.next || btn.dataset.back;
      if (target === 'done') {
        const choice = document.querySelector('input[name=choice]:checked').value;
        const payload = {
          model_dir: modelDirInput.value
            .replace(/^~/, document.body.dataset.home || '')
            .replace(/^%USERPROFILE%/, document.body.dataset.userprofile || ''),
          provider: choice,
          default_model: document.getElementById('default_model').value || ''
        };
        show('done');
        document.getElementById('done_status').textContent = 'Saving...';
        const r = await fetch('/api/save', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        document.getElementById('done_status').textContent = r.ok
          ? 'Saved. You can close this window.'
          : 'Error saving config; check logs.';
      } else {
        show(target);
      }
    });
  });

  show('welcome');
})();

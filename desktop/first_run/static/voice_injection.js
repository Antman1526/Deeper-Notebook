// desktop/first_run/static/voice_injection.js
// Injected into the main UI by desktop/window.py after page load. Adds:
//   - Floating microphone button (press-and-hold to record, sends to /api/transcribe)
//   - Per-message speaker icon (click to play assistant message via TTS)
(function () {
  if (window.__ONP_VOICE_INJECTED) return;
  window.__ONP_VOICE_INJECTED = true;

  const STT_URL = (window.ONP_STT_URL || '/api/transcribe');
  const TTS_URL = (window.ONP_TTS_URL || '/api/audio/speech');

  // --- Mic FAB ---
  const fab = document.createElement('button');
  fab.id = 'onp-mic-fab';
  fab.innerHTML = '🎤';
  fab.title = 'Hold to record · Release to send';
  Object.assign(fab.style, {
    position: 'fixed', bottom: '24px', right: '24px',
    width: '52px', height: '52px', borderRadius: '50%',
    background: 'var(--primary, #2D7FF9)', color: 'var(--on-primary, #fff)',
    border: '1px solid var(--border, #ccc)', fontSize: '24px',
    cursor: 'pointer', zIndex: '99999',
    boxShadow: '0 4px 16px rgba(0,0,0,0.18)',
  });
  document.body.appendChild(fab);

  let mediaRecorder = null;
  let chunks = [];
  fab.addEventListener('mousedown', async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      chunks = [];
      mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
      mediaRecorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        const form = new FormData();
        form.append('file', blob, 'clip.webm');
        form.append('model', 'whisper-base-en');
        fab.innerHTML = '⌛';
        try {
          const r = await fetch(STT_URL, { method: 'POST', body: form });
          const data = await r.json();
          const input = document.querySelector('textarea, [contenteditable=true]');
          if (input) {
            if (input.tagName === 'TEXTAREA') {
              input.value = (input.value || '') + data.text;
              input.dispatchEvent(new Event('input', { bubbles: true }));
            } else {
              input.textContent = (input.textContent || '') + data.text;
            }
          }
        } catch (e) {
          console.error('STT failed', e);
        }
        fab.innerHTML = '🎤';
        stream.getTracks().forEach(t => t.stop());
      };
      mediaRecorder.start();
      fab.innerHTML = '🔴';
    } catch (e) {
      console.error('mic permission denied or recording failed', e);
    }
  });
  fab.addEventListener('mouseup', () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
  });
  fab.addEventListener('mouseleave', () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
  });

  // --- Per-message speaker buttons ---
  function injectSpeakerButtons() {
    const candidates = document.querySelectorAll(
      '[data-role="assistant"], .message-assistant, [aria-label*="assistant"]'
    );
    candidates.forEach((node) => {
      if (node.querySelector('.onp-speaker-btn')) return;
      const btn = document.createElement('button');
      btn.className = 'onp-speaker-btn';
      btn.innerHTML = '🔊';
      btn.title = 'Play this response';
      Object.assign(btn.style, {
        marginLeft: '8px', background: 'transparent', border: 'none',
        cursor: 'pointer', fontSize: '14px', opacity: '0.6',
      });
      btn.addEventListener('click', async () => {
        const text = node.innerText;
        try {
          btn.innerHTML = '⌛';
          const r = await fetch(TTS_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input: text, voice: 'alex',
                                   model: 'piper-amy-en' }),
          });
          const blob = await r.blob();
          const url = URL.createObjectURL(blob);
          new Audio(url).play();
        } catch (e) {
          console.error('TTS failed', e);
        } finally {
          btn.innerHTML = '🔊';
        }
      });
      node.appendChild(btn);
    });
  }
  const observer = new MutationObserver(injectSpeakerButtons);
  observer.observe(document.body, { childList: true, subtree: true });
  injectSpeakerButtons();
})();

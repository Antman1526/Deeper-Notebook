// desktop/first_run/static/voice_injection.js
// Injected into the main UI by desktop/window.py after page load. Adds:
//   - Floating microphone button (press-and-hold to record, sends to /api/transcribe)
//     + CSS pulse ring while recording + live audio-level bars + SVG spinner
//     + fade-in/out toast when transcription completes
//   - Per-message speaker icon (click to play assistant message via TTS)
//     + stop button, inline progress bar
//   - Toast notifications for errors and successes
(function () {
  if (window.__DEEPER_NOTEBOOK_VOICE_INJECTED) return;
  window.__DEEPER_NOTEBOOK_VOICE_INJECTED = true;

  const STT_URL = (
    window.DEEPER_NOTEBOOK_STT_URL || window.ONP_STT_URL || '/api/transcribe'
  );
  const TTS_URL = (
    window.DEEPER_NOTEBOOK_TTS_URL || window.ONP_TTS_URL || '/api/audio/speech'
  );

  // ---------------------------------------------------------------------------
  // Inject global styles
  // ---------------------------------------------------------------------------
  (function injectStyles() {
    const style = document.createElement('style');
    style.textContent = [
      // Pulse ring around mic FAB while recording
      '@keyframes onp-pulse {',
      '  0%   { box-shadow: 0 0 0 0 rgba(var(--dn-pulse-rgb,45,212,191), 0.55); }',
      '  70%  { box-shadow: 0 0 0 14px rgba(var(--dn-pulse-rgb,45,212,191), 0); }',
      '  100% { box-shadow: 0 0 0 0 rgba(var(--dn-pulse-rgb,45,212,191), 0); }',
      '}',
      '#onp-mic-fab.recording { animation: onp-pulse 1.1s ease-out infinite; }',

      // SVG spinner (used by both mic and speaker)
      '@keyframes onp-spin { to { transform: rotate(360deg); } }',
      '.onp-spinner { display:inline-block; animation: onp-spin 0.8s linear infinite; }',

      // Audio level bars
      '#onp-level-bars {',
      '  position: fixed; bottom: 82px; right: 28px;',
      '  display: flex; align-items: flex-end; gap: 3px;',
      '  height: 20px; z-index: 99998; opacity: 0;',
      '  transition: opacity 0.2s;',
      '}',
      '#onp-level-bars.visible { opacity: 1; }',
      '#onp-level-bars span {',
      '  width: 4px; border-radius: 2px;',
      '  background: var(--primary, #2D7FF9);',
      '  transition: height 0.06s linear;',
      '}',

      // Toast container
      '#onp-toast-container {',
      '  position: fixed; top: 16px; left: 50%; transform: translateX(-50%);',
      '  z-index: 999999; display: flex; flex-direction: column; gap: 8px;',
      '  pointer-events: none;',
      '}',
      '.onp-toast {',
      '  min-width: 240px; max-width: 420px;',
      '  background: var(--surface, #fff); color: var(--text, #222);',
      '  border-radius: 8px; padding: 10px 14px;',
      '  font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;',
      '  box-shadow: 0 4px 20px rgba(0,0,0,0.18);',
      '  display: flex; align-items: center; gap: 10px;',
      '  pointer-events: auto;',
      '  transition: opacity 0.3s, transform 0.3s;',
      '  opacity: 0; transform: translateY(-8px);',
      '}',
      '.onp-toast.show { opacity: 1; transform: translateY(0); }',
      '.onp-toast.success { border-left: 4px solid #22c55e; }',
      '.onp-toast.error   { border-left: 4px solid #ef4444; }',
      '.onp-toast .onp-toast-msg { flex: 1; }',
      '.onp-toast .onp-toast-close {',
      '  background: transparent; border: none; cursor: pointer;',
      '  font-size: 14px; color: var(--muted, #888); line-height: 1;',
      '  padding: 0 2px;',
      '}',

      // Inline audio progress bar
      '.onp-audio-bar-wrap {',
      '  display: inline-flex; align-items: center; gap: 6px;',
      '  vertical-align: middle; margin-left: 6px;',
      '}',
      '.onp-audio-bar {',
      '  width: 80px; height: 4px; border-radius: 2px;',
      '  background: var(--border, #ddd); overflow: hidden;',
      '}',
      '.onp-audio-bar-fill {',
      '  height: 100%; width: 0%; border-radius: 2px;',
      '  background: var(--primary, #2D7FF9); transition: width 0.25s linear;',
      '}',
    ].join('\n');
    document.head.appendChild(style);
  }());

  // ---------------------------------------------------------------------------
  // SVG spinner helper
  // ---------------------------------------------------------------------------
  function spinnerSVG() {
    return '<svg class="onp-spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">' +
           '<path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>' +
           '</svg>';
  }

  // ---------------------------------------------------------------------------
  // Toast system
  // ---------------------------------------------------------------------------
  var toastContainer = document.createElement('div');
  toastContainer.id = 'onp-toast-container';
  document.body.appendChild(toastContainer);

  function showToast(msg, type, durationMs) {
    // type: 'success' | 'error'
    // durationMs: auto-dismiss timeout (0 = manual only)
    var dur = (durationMs === undefined) ? (type === 'success' ? 3000 : 0) : durationMs;
    var toast = document.createElement('div');
    toast.className = 'onp-toast ' + (type || 'success');
    var msgSpan = document.createElement('span');
    msgSpan.className = 'onp-toast-msg';
    msgSpan.textContent = msg;
    var closeBtn = document.createElement('button');
    closeBtn.className = 'onp-toast-close';
    closeBtn.setAttribute('aria-label', 'Close notification');
    closeBtn.textContent = '✕';
    closeBtn.addEventListener('click', function () { dismissToast(toast); });
    toast.appendChild(msgSpan);
    toast.appendChild(closeBtn);
    toastContainer.appendChild(toast);
    // Trigger transition
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { toast.classList.add('show'); });
    });
    if (dur > 0) {
      setTimeout(function () { dismissToast(toast); }, dur);
    }
    return toast;
  }

  function dismissToast(toast) {
    toast.classList.remove('show');
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 350);
  }

  // ---------------------------------------------------------------------------
  // Mic FAB
  // ---------------------------------------------------------------------------
  var fab = document.createElement('button');
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
    transition: 'transform 0.15s',
  });
  document.body.appendChild(fab);

  // ---------------------------------------------------------------------------
  // Audio level bars
  // ---------------------------------------------------------------------------
  var levelBarsEl = document.createElement('div');
  levelBarsEl.id = 'onp-level-bars';
  var BAR_COUNT = 5;
  var barEls = [];
  for (var bi = 0; bi < BAR_COUNT; bi++) {
    var bar = document.createElement('span');
    bar.style.height = '4px';
    levelBarsEl.appendChild(bar);
    barEls.push(bar);
  }
  document.body.appendChild(levelBarsEl);

  var _audioCtx = null;
  var _analyser = null;
  var _levelRaf = null;

  function startLevelMeter(stream) {
    levelBarsEl.classList.add('visible');
    try {
      _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      _analyser = _audioCtx.createAnalyser();
      _analyser.fftSize = 256;
      _audioCtx.createMediaStreamSource(stream).connect(_analyser);
      var buf = new Uint8Array(_analyser.frequencyBinCount);
      function tick() {
        _analyser.getByteFrequencyData(buf);
        // Use first BAR_COUNT non-trivially spaced bins as "bands"
        var step = Math.floor(buf.length / (BAR_COUNT + 1));
        for (var i = 0; i < BAR_COUNT; i++) {
          var v = buf[(i + 1) * step] / 255;
          barEls[i].style.height = Math.max(4, Math.round(v * 20)) + 'px';
        }
        _levelRaf = requestAnimationFrame(tick);
      }
      tick();
    } catch (e) {
      // silently ignore — level meter is decorative
    }
  }

  function stopLevelMeter() {
    levelBarsEl.classList.remove('visible');
    if (_levelRaf) { cancelAnimationFrame(_levelRaf); _levelRaf = null; }
    if (_audioCtx) {
      try { _audioCtx.close(); } catch (e) { /* ignore */ }
      _audioCtx = null; _analyser = null;
    }
    barEls.forEach(function (b) { b.style.height = '4px'; });
  }

  // ---------------------------------------------------------------------------
  // Recording logic
  // ---------------------------------------------------------------------------
  var mediaRecorder = null;
  var chunks = [];

  fab.addEventListener('mousedown', function () {
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      mediaRecorder = new MediaRecorder(stream);
      chunks = [];
      mediaRecorder.ondataavailable = function (e) { chunks.push(e.data); };
      mediaRecorder.onstop = function () {
        stopLevelMeter();
        fab.classList.remove('recording');
        var blob = new Blob(chunks, { type: 'audio/webm' });
        var form = new FormData();
        form.append('file', blob, 'clip.webm');
        form.append('model', 'whisper-base-en');
        fab.innerHTML = spinnerSVG();
        fetch(STT_URL, { method: 'POST', body: form })
          .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
          })
          .then(function (data) {
            var text = (data.text || '').trim();
            var input = document.querySelector('textarea, [contenteditable=true]');
            if (input) {
              if (input.tagName === 'TEXTAREA') {
                input.value = (input.value || '') + text;
                input.dispatchEvent(new Event('input', { bubbles: true }));
              } else {
                input.textContent = (input.textContent || '') + text;
              }
            }
            var preview = text.length > 40 ? text.slice(0, 40) + '…' : text;
            showToast('Transcribed: “' + preview + '”', 'success', 3000);
          })
          .catch(function (e) {
            var msg = (e instanceof TypeError) ? 'Network error' : ('STT failed: ' + e.message);
            showToast(msg, 'error');
          })
          .finally(function () {
            fab.innerHTML = '🎤';
            stream.getTracks().forEach(function (t) { t.stop(); });
          });
      };
      mediaRecorder.start();
      fab.classList.add('recording');
      fab.innerHTML = '🔴';
      startLevelMeter(stream);
    }).catch(function (e) {
      showToast('Microphone permission denied', 'error');
      console.error('mic permission denied or recording failed', e);
    });
  });

  fab.addEventListener('mouseup', function () {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
  });
  fab.addEventListener('mouseleave', function () {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
  });

  // ---------------------------------------------------------------------------
  // Per-message speaker buttons  (audio player with stop + progress bar)
  // ---------------------------------------------------------------------------
  var _currentAudio = null;
  var _currentProgressFill = null;
  var _currentSpeakerBtn = null;

  var SPEAKER_ICON = '🔊';
  var STOP_ICON = '<svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><rect x="2" y="2" width="12" height="12" rx="2"/></svg>';

  function stopCurrentAudio() {
    if (_currentAudio) {
      _currentAudio.pause();
      _currentAudio.currentTime = 0;
      URL.revokeObjectURL(_currentAudio.src);  // free blob memory
      _currentAudio = null;
    }
    if (_currentProgressFill) {
      _currentProgressFill.style.width = '0%';
      _currentProgressFill = null;
    }
    if (_currentSpeakerBtn) {
      _currentSpeakerBtn.innerHTML = SPEAKER_ICON;
      _currentSpeakerBtn.title = 'Play this response';
      _currentSpeakerBtn.style.opacity = '0.6';
      _currentSpeakerBtn = null;
    }
  }

  function injectSpeakerButtons() {
    var candidates = document.querySelectorAll(
      '[data-role="assistant"], .message-assistant, [aria-label*="assistant"]'
    );
    candidates.forEach(function (node) {
      if (node.querySelector('.onp-speaker-btn')) return;

      var btn = document.createElement('button');
      btn.className = 'onp-speaker-btn';
      btn.innerHTML = SPEAKER_ICON;
      btn.title = 'Play this response';
      Object.assign(btn.style, {
        marginLeft: '8px', background: 'transparent', border: 'none',
        cursor: 'pointer', fontSize: '14px', opacity: '0.6',
        verticalAlign: 'middle',
      });

      // Inline progress bar wrapper
      var barWrap = document.createElement('span');
      barWrap.className = 'onp-audio-bar-wrap';
      barWrap.style.display = 'none';
      var barTrack = document.createElement('span');
      barTrack.className = 'onp-audio-bar';
      var barFill = document.createElement('span');
      barFill.className = 'onp-audio-bar-fill';
      barTrack.appendChild(barFill);
      barWrap.appendChild(barTrack);

      btn.addEventListener('click', function () {
        // If this button is currently playing — stop it.
        if (_currentSpeakerBtn === btn) {
          stopCurrentAudio();
          barWrap.style.display = 'none';
          return;
        }
        // Stop anything else already playing.
        stopCurrentAudio();

        var text = node.innerText;
        btn.innerHTML = spinnerSVG();
        barWrap.style.display = 'none';

        fetch(TTS_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ input: text, voice: 'alex', model: 'piper-amy-en' }),
        })
          .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.blob();
          })
          .then(function (blob) {
            var url = URL.createObjectURL(blob);
            var audio = new Audio(url);
            _currentAudio = audio;
            _currentProgressFill = barFill;
            _currentSpeakerBtn = btn;

            barFill.style.width = '0%';
            barWrap.style.display = 'inline-flex';
            btn.innerHTML = STOP_ICON;
            btn.title = 'Stop playback';
            btn.style.opacity = '1';

            audio.addEventListener('timeupdate', function () {
              if (audio.duration) {
                barFill.style.width = (audio.currentTime / audio.duration * 100) + '%';
              }
            });
            audio.addEventListener('ended', function () {
              stopCurrentAudio();
              barWrap.style.display = 'none';
            });
            audio.play().catch(function (e) {
              showToast('TTS failed: ' + e.message, 'error');
              stopCurrentAudio();
              barWrap.style.display = 'none';
            });
            showToast('Voice ready', 'success', 2000);
          })
          .catch(function (e) {
            var msg = (e instanceof TypeError) ? 'Network error' : ('TTS failed: ' + e.message);
            showToast(msg, 'error');
            btn.innerHTML = SPEAKER_ICON;
            btn.title = 'Play this response';
            barWrap.style.display = 'none';
          });
      });

      node.appendChild(btn);
      node.appendChild(barWrap);
    });
  }

  var observer = new MutationObserver(injectSpeakerButtons);
  observer.observe(document.body, { childList: true, subtree: true });
  injectSpeakerButtons();
}());

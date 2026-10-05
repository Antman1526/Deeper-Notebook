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

  // v0.8.130 — every user-visible string this script produces, in the app's 14
  // languages (same keys as MEMORY_LABELS in memory_injection.js). Strict JSON so
  // desktop/tests/test_desktop_injections.py can parse it. {name} marks a value
  // inserted at call time. Italian follows the app's own terms ("riconoscimento
  // vocale", "sintesi vocale").
  var VOICE_STRINGS = {
    "en": {"mic.title": "Hold to record · Release to send", "speaker.play": "Play this response", "speaker.stop": "Stop playback", "toast.transcribed": "Transcribed: “{text}”", "toast.networkError": "Network error", "toast.sttFailed": "STT failed: {error}", "toast.micDenied": "Microphone permission denied", "toast.ttsFailed": "TTS failed: {error}", "toast.voiceReady": "Voice ready", "toast.close": "Close notification"},
    "de": {"mic.title": "Zum Aufnehmen halten · Zum Senden loslassen", "speaker.play": "Diese Antwort vorlesen", "speaker.stop": "Wiedergabe stoppen", "toast.transcribed": "Transkribiert: „{text}“", "toast.networkError": "Netzwerkfehler", "toast.sttFailed": "Spracherkennung fehlgeschlagen: {error}", "toast.micDenied": "Mikrofonzugriff verweigert", "toast.ttsFailed": "Sprachausgabe fehlgeschlagen: {error}", "toast.voiceReady": "Sprachausgabe bereit", "toast.close": "Benachrichtigung schließen"},
    "es": {"mic.title": "Mantén pulsado para grabar · Suelta para enviar", "speaker.play": "Reproducir esta respuesta", "speaker.stop": "Detener la reproducción", "toast.transcribed": "Transcrito: «{text}»", "toast.networkError": "Error de red", "toast.sttFailed": "Error en el reconocimiento de voz: {error}", "toast.micDenied": "Permiso de micrófono denegado", "toast.ttsFailed": "Error en la síntesis de voz: {error}", "toast.voiceReady": "Voz lista", "toast.close": "Cerrar notificación"},
    "ca": {"mic.title": "Mantén premut per gravar · Deixa anar per enviar", "speaker.play": "Reprodueix aquesta resposta", "speaker.stop": "Atura la reproducció", "toast.transcribed": "Transcrit: «{text}»", "toast.networkError": "Error de xarxa", "toast.sttFailed": "Ha fallat el reconeixement de veu: {error}", "toast.micDenied": "Permís del micròfon denegat", "toast.ttsFailed": "Ha fallat la síntesi de veu: {error}", "toast.voiceReady": "Veu a punt", "toast.close": "Tanca la notificació"},
    "fr": {"mic.title": "Maintenez pour enregistrer · Relâchez pour envoyer", "speaker.play": "Lire cette réponse", "speaker.stop": "Arrêter la lecture", "toast.transcribed": "Transcrit : « {text} »", "toast.networkError": "Erreur réseau", "toast.sttFailed": "Échec de la reconnaissance vocale : {error}", "toast.micDenied": "Autorisation du microphone refusée", "toast.ttsFailed": "Échec de la synthèse vocale : {error}", "toast.voiceReady": "Voix prête", "toast.close": "Fermer la notification"},
    "it": {"mic.title": "Tieni premuto per registrare · Rilascia per inviare", "speaker.play": "Riproduci questa risposta", "speaker.stop": "Interrompi la riproduzione", "toast.transcribed": "Trascritto: «{text}»", "toast.networkError": "Errore di rete", "toast.sttFailed": "Riconoscimento vocale non riuscito: {error}", "toast.micDenied": "Autorizzazione al microfono negata", "toast.ttsFailed": "Sintesi vocale non riuscita: {error}", "toast.voiceReady": "Voce pronta", "toast.close": "Chiudi notifica"},
    "pt": {"mic.title": "Segure para gravar · Solte para enviar", "speaker.play": "Reproduzir esta resposta", "speaker.stop": "Parar a reprodução", "toast.transcribed": "Transcrito: “{text}”", "toast.networkError": "Erro de rede", "toast.sttFailed": "Falha no reconhecimento de fala: {error}", "toast.micDenied": "Permissão de microfone negada", "toast.ttsFailed": "Falha na síntese de fala: {error}", "toast.voiceReady": "Voz pronta", "toast.close": "Fechar notificação"},
    "pl": {"mic.title": "Przytrzymaj, aby nagrywać · Puść, aby wysłać", "speaker.play": "Odtwórz tę odpowiedź", "speaker.stop": "Zatrzymaj odtwarzanie", "toast.transcribed": "Transkrypcja: „{text}”", "toast.networkError": "Błąd sieci", "toast.sttFailed": "Rozpoznawanie mowy nie powiodło się: {error}", "toast.micDenied": "Odmowa dostępu do mikrofonu", "toast.ttsFailed": "Synteza mowy nie powiodła się: {error}", "toast.voiceReady": "Głos gotowy", "toast.close": "Zamknij powiadomienie"},
    "ru": {"mic.title": "Удерживайте, чтобы записать · Отпустите, чтобы отправить", "speaker.play": "Воспроизвести этот ответ", "speaker.stop": "Остановить воспроизведение", "toast.transcribed": "Распознано: «{text}»", "toast.networkError": "Ошибка сети", "toast.sttFailed": "Не удалось распознать речь: {error}", "toast.micDenied": "Доступ к микрофону запрещён", "toast.ttsFailed": "Не удалось синтезировать речь: {error}", "toast.voiceReady": "Голос готов", "toast.close": "Закрыть уведомление"},
    "tr": {"mic.title": "Kaydetmek için basılı tutun · Göndermek için bırakın", "speaker.play": "Bu yanıtı oynat", "speaker.stop": "Oynatmayı durdur", "toast.transcribed": "Metne dönüştürüldü: “{text}”", "toast.networkError": "Ağ hatası", "toast.sttFailed": "Konuşma tanıma başarısız: {error}", "toast.micDenied": "Mikrofon izni reddedildi", "toast.ttsFailed": "Konuşma sentezi başarısız: {error}", "toast.voiceReady": "Ses hazır", "toast.close": "Bildirimi kapat"},
    "ja": {"mic.title": "押している間録音 · 離すと送信", "speaker.play": "この回答を再生", "speaker.stop": "再生を停止", "toast.transcribed": "文字起こししました: 「{text}」", "toast.networkError": "ネットワークエラー", "toast.sttFailed": "音声認識に失敗しました: {error}", "toast.micDenied": "マイクの使用が許可されませんでした", "toast.ttsFailed": "音声合成に失敗しました: {error}", "toast.voiceReady": "音声の準備ができました", "toast.close": "通知を閉じる"},
    "zh-CN": {"mic.title": "按住录音 · 松开发送", "speaker.play": "播放此回复", "speaker.stop": "停止播放", "toast.transcribed": "已转写：“{text}”", "toast.networkError": "网络错误", "toast.sttFailed": "语音识别失败：{error}", "toast.micDenied": "麦克风权限被拒绝", "toast.ttsFailed": "语音合成失败：{error}", "toast.voiceReady": "语音已就绪", "toast.close": "关闭通知"},
    "zh-TW": {"mic.title": "按住錄音 · 放開傳送", "speaker.play": "播放此回覆", "speaker.stop": "停止播放", "toast.transcribed": "已轉錄：「{text}」", "toast.networkError": "網路錯誤", "toast.sttFailed": "語音辨識失敗：{error}", "toast.micDenied": "麥克風權限遭拒", "toast.ttsFailed": "語音合成失敗：{error}", "toast.voiceReady": "語音已就緒", "toast.close": "關閉通知"},
    "bn": {"mic.title": "রেকর্ড করতে চেপে ধরুন · পাঠাতে ছেড়ে দিন", "speaker.play": "এই উত্তরটি চালান", "speaker.stop": "প্লেব্যাক বন্ধ করুন", "toast.transcribed": "ট্রান্সক্রিপ্ট হয়েছে: “{text}”", "toast.networkError": "নেটওয়ার্ক ত্রুটি", "toast.sttFailed": "স্পিচ রিকগনিশন ব্যর্থ হয়েছে: {error}", "toast.micDenied": "মাইক্রোফোনের অনুমতি প্রত্যাখ্যাত হয়েছে", "toast.ttsFailed": "স্পিচ সিন্থেসিস ব্যর্থ হয়েছে: {error}", "toast.voiceReady": "ভয়েস প্রস্তুত", "toast.close": "বিজ্ঞপ্তি বন্ধ করুন"}
  };

  // Resolve at call time, not load time: the interface language can change while
  // the app is open. Exact tag, then base language, then English.
  function voiceTable() {
    var lang = document.documentElement.lang || 'en';
    if (VOICE_STRINGS[lang]) return VOICE_STRINGS[lang];
    var base = lang.split('-')[0];
    if (VOICE_STRINGS[base]) return VOICE_STRINGS[base];
    if (base === 'zh') {
      return /hant|-tw|-hk|-mo/i.test(lang) ? VOICE_STRINGS['zh-TW'] : VOICE_STRINGS['zh-CN'];
    }
    return VOICE_STRINGS.en;
  }

  function vt(key, vars) {
    var text = voiceTable()[key];
    if (text === undefined) text = VOICE_STRINGS.en[key];
    if (text === undefined) text = key;
    return text.replace(/\{(\w+)\}/g, function (m, name) {
      return (vars && vars[name] !== undefined) ? String(vars[name]) : m;
    });
  }

  // Tooltip and accessible name together: these buttons are icon-only, so
  // without an aria-label a screen reader announces nothing useful.
  function setLabel(el, key) {
    var text = vt(key);
    el.title = text;
    el.setAttribute('aria-label', text);
  }

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
      '#onp-mic-fab.recording { animation: onp-pulse 1.1s ease-out infinite; background: var(--destructive, #dc2626) !important; color: #fff !important; }',
      '#onp-mic-fab:active { transform: scale(0.96); }',

      // SVG spinner (used by both mic and speaker)
      '@keyframes onp-spin { to { transform: rotate(360deg); } }',
      '.onp-spinner { display:inline-block; animation: onp-spin 0.8s linear infinite; }',

      // Audio level bars
      '#onp-level-bars {',
      '  position: fixed; bottom: 76px; right: 28px;',
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
      '  background: var(--card, #fff); color: var(--card-foreground, #222);',
      '  border: 1px solid var(--border, #ddd);',
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
      '  font-size: 14px; color: var(--muted-foreground, #888); line-height: 1;',
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
    closeBtn.setAttribute('aria-label', vt('toast.close'));
    closeBtn.textContent = '\u00D7';
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
  // v0.8.130 — drawn icons in the app's own tokens: the emoji glyphs and the circle did
  // not match the interface, and `--on-primary` is not a token the app defines.
  var MIC_ICON = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19v3"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><rect x="9" y="2" width="6" height="13" rx="3"/></svg>';
  var RECORDING_ICON = '<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="2" y="2" width="12" height="12" rx="2"/></svg>';
  var fab = document.createElement('button');
  fab.id = 'onp-mic-fab';
  fab.innerHTML = MIC_ICON;
  setLabel(fab, 'mic.title');
  Object.assign(fab.style, {
    position: 'fixed', bottom: '24px', right: '24px',
    width: '44px', height: '44px', borderRadius: '10px',
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    background: 'var(--primary, #2D7FF9)', color: 'var(--primary-foreground, #fff)',
    border: 'none', padding: '0',
    cursor: 'pointer', zIndex: '99999',
    boxShadow: '0 1px 2px rgba(0,0,0,0.12), 0 10px 22px -12px rgba(0,0,0,0.45)',
    transition: 'transform 0.15s, background-color 0.15s',
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
            showToast(vt('toast.transcribed', { text: preview }), 'success', 3000);
          })
          .catch(function (e) {
            var msg = (e instanceof TypeError) ? vt('toast.networkError') : vt('toast.sttFailed', { error: e.message });
            showToast(msg, 'error');
          })
          .finally(function () {
            fab.innerHTML = MIC_ICON;
            stream.getTracks().forEach(function (t) { t.stop(); });
          });
      };
      mediaRecorder.start();
      fab.classList.add('recording');
      fab.innerHTML = RECORDING_ICON;
      startLevelMeter(stream);
    }).catch(function (e) {
      showToast(vt('toast.micDenied'), 'error');
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

  var SPEAKER_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4.7a.7.7 0 0 0-1.2-.5L6.4 7.6A1.4 1.4 0 0 1 5.4 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.4a1.4 1.4 0 0 1 1 .4l3.4 3.4a.7.7 0 0 0 1.2-.5z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.4 18.4a9 9 0 0 0 0-12.8"/></svg>';
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
      setLabel(_currentSpeakerBtn, 'speaker.play');
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
      setLabel(btn, 'speaker.play');
      Object.assign(btn.style, {
        marginLeft: '8px', background: 'transparent', border: 'none',
        cursor: 'pointer', fontSize: '14px', opacity: '0.6', color: 'inherit',
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
            setLabel(btn, 'speaker.stop');
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
              showToast(vt('toast.ttsFailed', { error: e.message }), 'error');
              stopCurrentAudio();
              barWrap.style.display = 'none';
            });
            showToast(vt('toast.voiceReady'), 'success', 2000);
          })
          .catch(function (e) {
            var msg = (e instanceof TypeError) ? vt('toast.networkError') : vt('toast.ttsFailed', { error: e.message });
            showToast(msg, 'error');
            btn.innerHTML = SPEAKER_ICON;
            setLabel(btn, 'speaker.play');
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

/* JARVIS core: shared by every interface theme.
   Handles talking to Python (eel), voice input with the wake word, chat polling,
   typed input, notifications, the mic level meter and the settings panel.

   A theme page loads /eel.js and this file, registers handlers, then calls JarvisCore.init():
     JarvisCore.on('messages', (list, isHistory) => ...)  // chat lines {role, name, text(escaped html)};
                                              // isHistory=true for the earlier conversation sent once on load
     JarvisCore.on('state', text => ...)      // "Listening - say ...", "Thinking...", "Speaking...", ...
     JarvisCore.on('listening', bool => ...)  // mic on/off
     JarvisCore.on('level', 0..1 => ...)      // live microphone loudness (if available)
     JarvisCore.init({ form, input, micButton, settingsButton });
*/
(function () {
    'use strict';
    var handlers = { messages: [], state: [], listening: [], level: [] };
    var pageId = Math.random().toString(36).slice(2);
    var polling = false;
    var firstBatch = true;
    var lastState = null;
    var listening = false;

    function emit(evt, value, extra) {
        handlers[evt].forEach(function (fn) {
            try { fn(value, extra); } catch (e) { console.error(e); }
        });
    }

    // ---------------- notifications ----------------
    var toast = null, toastTimer = null;
    function notify(text, ms) {
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 'jc-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = text;
        toast.classList.add('jc-show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { toast.classList.remove('jc-show'); }, ms || 3500);
    }

    // ---------------- polling Python ----------------
    function poll() {
        if (!polling) {
            polling = true;
            eel.js_messages(pageId)(function (list) {
                polling = false;
                var isHistory = firstBatch;
                firstBatch = false;
                if (list && list.length) emit('messages', list, isHistory);
            });
        }
        eel.js_state()(function (s) {
            if (s !== lastState) { lastState = s; emit('state', s); }
        });
    }

    // ---------------- typed input ----------------
    function send(text, inputEl) {
        text = (text || '').trim();
        if (!text) return;
        if (text === '/settings') { openSettings(); return; }
        eel.js_mic(text, false)(function (accepted) {
            if (!accepted) {
                if (inputEl && !inputEl.value) inputEl.value = text;
                notify('JARVIS is still busy - try again in a moment.');
            }
        });
    }

    // ---------------- voice input ----------------
    var voice = (function () {
        var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) return null;
        var rec = new SR();
        rec.continuous = true;
        rec.interimResults = false;
        rec.maxAlternatives = 1;
        var want = false, running = false, blocked = false;
        var startSound = new Audio('/assets/activation_sound.wav');
        var stopSound = new Audio('/assets/deactivation_sound.wav');

        function engineStart() {
            if (!want || running) return;
            try { rec.start(); } catch (e) { /* already starting */ }
        }
        function set(on, withSound) {
            want = on;
            listening = on;
            emit('listening', on);
            eel.js_state(on ? 'Listening...' : 'Available...');
            if (withSound) { var a = on ? startSound : stopSound; a.currentTime = 0; a.play().catch(function () {}); }
            if (on) { blocked = false; engineStart(); if (!meterStarted) startMeter(); }
            else { try { rec.stop(); } catch (e) {} }
        }
        rec.onstart = function () { running = true; };
        rec.onend = function () {
            running = false;
            if (want && !blocked) setTimeout(engineStart, 300); // browsers stop after silence: restart
        };
        rec.onerror = function (event) {
            if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                blocked = true;
                set(false, false);
                notify('🎤 Click anywhere to turn on the microphone (then click "Allow").', 10000);
                document.addEventListener('click', function enable(e) {
                    document.removeEventListener('click', enable, true);
                    if (e.target.closest && e.target.closest('[data-jc-mic]')) return; // mic button toggles itself
                    set(true, true);
                }, true);
            } else if (event.error !== 'no-speech' && event.error !== 'aborted') {
                console.warn('Speech recognition error:', event.error);
            }
        };
        rec.onresult = function (event) {
            for (var i = event.resultIndex; i < event.results.length; i++) {
                if (event.results[i].isFinal) {
                    var text = event.results[i][0].transcript.trim();
                    if (text) eel.js_mic(text, true);
                }
            }
        };
        return {
            setLang: function (l) { rec.lang = l || 'en-US'; },
            set: set,
            toggle: function () { set(!want, true); },
            isOn: function () { return want; }
        };
    })();

    // ---------------- microphone level meter (for visuals only) ----------------
    var meterStarted = false;
    function startMeter() {
        meterStarted = true;
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.AudioContext) return;
        navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
            var ctx = new AudioContext();
            var analyser = ctx.createAnalyser();
            analyser.fftSize = 512;
            ctx.createMediaStreamSource(stream).connect(analyser);
            var data = new Uint8Array(analyser.fftSize);
            (function tick() {
                analyser.getByteTimeDomainData(data);
                var sum = 0;
                for (var i = 0; i < data.length; i++) { var v = (data[i] - 128) / 128; sum += v * v; }
                emit('level', Math.min(1, Math.sqrt(sum / data.length) * 4));
                requestAnimationFrame(tick);
            })();
        }).catch(function () { /* no meter; voice still works */ });
    }

    // ---------------- settings panel (same in every theme) ----------------
    var panel = null;
    function openSettings() {
        if (!panel) buildPanel();
        eel.js_getsettings()(function (c) {
            var f = panel.querySelector('form');
            f.groq.value = '';
            f.groq.placeholder = c.groq_set ? 'Saved' + (c.groq_hint ? ' (' + c.groq_hint + ')' : '') + ' - paste a new key to replace' : 'Not set';
            f.gemini.value = '';
            f.gemini.placeholder = c.gemini_set ? 'Saved' + (c.gemini_hint ? ' (' + c.gemini_hint + ')' : '') + ' - paste a new key to replace' : 'Not set (recommended)';
            f.provider.value = c.provider || 'auto';
            f.use_ollama.checked = !!c.use_ollama;
            panel.querySelector('.jc-models').textContent = c.models && c.models.length
                ? 'In use: ' + c.models.slice(0, 3).join(', ') + (c.vision && c.vision.length ? ' | images: ' + c.vision[0] : ' | images: none')
                : 'No AI connected yet - add a key above.';
            f.user.value = c.user || '';
            f.assistant.value = c.assistant || '';
            f.language.value = c.language || 'en-US';
            f.wake_word.checked = !!c.wake_word;
            f.country_code.value = c.country_code || '';
            f.email.value = c.email || '';
            f.email_password.value = '';
            f.email_password.placeholder = c.email_password_set ? 'Saved - type a new one to replace' : 'Not set';
            var sel = f.theme;
            sel.innerHTML = '';
            c.themes.forEach(function (t) {
                var o = document.createElement('option');
                o.value = t.id; o.textContent = t.name; o.selected = (t.id === c.theme);
                sel.appendChild(o);
            });
            panel.classList.add('jc-open');
        });
    }
    function buildPanel() {
        panel = document.createElement('div');
        panel.className = 'jc-overlay';
        panel.innerHTML =
            '<form class="jc-panel" autocomplete="off">' +
            '<h2>Settings</h2>' +
            '<label>Interface<select name="theme"></select></label>' +
            '<label>AI provider<select name="provider">' +
            '<option value="auto">Automatic - use every provider below that is set up</option>' +
            '<option value="gemini">Google Gemini first</option><option value="groq">Groq first</option>' +
            '<option value="ollama">Ollama first (open-source, runs on this PC)</option></select></label>' +
            '<label>Google Gemini API key - free at aistudio.google.com/apikey<input name="gemini" type="password"></label>' +
            '<label>Groq API key - free at console.groq.com/keys<input name="groq" type="password"></label>' +
            '<label class="jc-check"><input name="use_ollama" type="checkbox"> Also use Ollama open-source models on this PC</label>' +
            '<div class="jc-models"></div>' +
            '<label>What should JARVIS call you?<input name="user" type="text"></label>' +
            '<label>Assistant name (also the wake word)<input name="assistant" type="text"></label>' +
            '<label>Speech language<input name="language" type="text" placeholder="en-US, en-GB, en-IN, sw-KE ..."></label>' +
            '<label class="jc-check"><input name="wake_word" type="checkbox"> Only respond to voice that starts with the wake word</label>' +
            '<h3>Messages &amp; email (optional)</h3>' +
            '<label>Phone country code for WhatsApp numbers starting with 0<input name="country_code" type="text" placeholder="e.g. 254"></label>' +
            '<label>Your email address (Gmail, Yahoo, iCloud, Zoho)<input name="email" type="text" placeholder="you@gmail.com"></label>' +
            '<label>Email app password - for Gmail create one at myaccount.google.com/apppasswords<input name="email_password" type="password"></label>' +
            '<div class="jc-buttons"><button type="button" class="jc-cancel">Cancel</button><button type="submit">Save</button></div>' +
            '</form>';
        document.body.appendChild(panel);
        var f = panel.querySelector('form');
        panel.addEventListener('click', function (e) { if (e.target === panel) panel.classList.remove('jc-open'); });
        f.querySelector('.jc-cancel').addEventListener('click', function () { panel.classList.remove('jc-open'); });
        f.addEventListener('submit', function (e) {
            e.preventDefault();
            var values = {
                groq: f.groq.value, gemini: f.gemini.value, provider: f.provider.value, use_ollama: f.use_ollama.checked,
                user: f.user.value, assistant: f.assistant.value,
                language: f.language.value, wake_word: f.wake_word.checked, theme: f.theme.value,
                country_code: f.country_code.value, email: f.email.value, email_password: f.email_password.value
            };
            notify('Saving...');
            eel.js_savesettings(values)(function (r) {
                if (!r.ok) { notify('⚠️ ' + r.message, 9000); return; }
                panel.classList.remove('jc-open');
                if (voice) voice.setLang(values.language);
                if (r.page && r.page !== window.location.pathname) { window.location.href = r.page; }
                else { notify('Settings saved.'); }
            });
        });
    }

    // ---------------- styles for toast + settings panel ----------------
    var css = document.createElement('style');
    css.textContent =
        '.jc-toast{position:fixed;top:16px;right:16px;max-width:420px;padding:12px 16px;border-radius:10px;background:#fff;color:#111;' +
        'font:14px/1.4 system-ui,Segoe UI,sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.35);z-index:10000;opacity:0;transform:translateY(-8px);' +
        'transition:opacity .2s,transform .2s;pointer-events:none}.jc-toast.jc-show{opacity:1;transform:none}' +
        '.jc-overlay{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:9999}' +
        '.jc-overlay.jc-open{display:flex}' +
        '.jc-overlay .jc-panel{display:block;position:relative;inset:auto;transform:none;margin:0;text-shadow:none;text-align:left;' +
        'width:min(440px,92vw);max-height:92vh;overflow:auto;background:#12161c;color:#e8eef5;border:1px solid #2a3442;border-radius:14px;' +
        'padding:22px 24px;font:14px/1.4 system-ui,Segoe UI,sans-serif;box-shadow:0 20px 60px rgba(0,0,0,.5)}' +
        '.jc-overlay .jc-models{margin:-4px 0 12px;font-size:12px;color:#7f93a8}' +
        '.jc-overlay .jc-panel h3{margin:18px 0 10px;font-size:14px;font-weight:600;color:#e8eef5}' +
        '.jc-overlay .jc-panel h2{margin:0 0 14px;font-size:18px;font-weight:600}' +
        '.jc-overlay .jc-panel label{display:block;margin:0 0 12px;color:#9fb0c3;font-size:13px}' +
        '.jc-overlay .jc-panel input[type=text],.jc-overlay .jc-panel input[type=password],.jc-overlay .jc-panel select{display:block;width:100%;box-sizing:border-box;margin-top:5px;' +
        'padding:9px 11px;border-radius:8px;border:1px solid #2f3b4b;background:#0b0e12;color:#fff;font:14px system-ui,Segoe UI,sans-serif;outline:none;flex:none;height:auto;text-shadow:none}' +
        '.jc-overlay .jc-panel input:focus,.jc-overlay .jc-panel select:focus{border-color:#4cc3ff}' +
        '.jc-overlay .jc-panel .jc-check{display:flex;gap:8px;align-items:center;color:#d5dee8}' +
        '.jc-overlay .jc-buttons{display:flex;justify-content:flex-end;gap:10px;margin-top:16px}' +
        '.jc-overlay .jc-buttons button{padding:9px 18px;border-radius:8px;border:0;font-size:14px;font-weight:600;cursor:pointer;background:#4cc3ff;color:#001018}' +
        '.jc-overlay .jc-buttons .jc-cancel{background:#2a3442;color:#e8eef5}';
    document.head.appendChild(css);

    // ---------------- public API ----------------
    window.JarvisCore = {
        on: function (evt, fn) { handlers[evt].push(fn); },
        notify: notify,
        send: send,
        openSettings: openSettings,
        toggleListening: function () { if (voice) voice.toggle(); else notify('Voice input needs Chrome or Edge. You can still type.'); },
        isListening: function () { return listening; },
        init: function (opts) {
            opts = opts || {};
            if (opts.form && opts.input) {
                opts.form.addEventListener('submit', function (e) {
                    e.preventDefault();
                    var t = opts.input.value;
                    opts.input.value = '';
                    send(t, opts.input);
                });
            }
            if (opts.micButton) {
                opts.micButton.setAttribute('data-jc-mic', '1');
                opts.micButton.addEventListener('click', window.JarvisCore.toggleListening);
            }
            if (opts.settingsButton) opts.settingsButton.addEventListener('click', openSettings);
            document.addEventListener('keydown', function (e) {
                if (e.ctrlKey && e.code === 'Space') { e.preventDefault(); window.JarvisCore.toggleListening(); }
                if (e.key === 'Escape' && panel) panel.classList.remove('jc-open');
            });
            setInterval(poll, 300);
            poll();
            if (!voice) { notify('Voice input needs Chrome or Edge. You can still type.', 8000); return; }
            eel.js_language()(function (lang) {
                voice.setLang(lang);
                if (opts.autoListen !== false) voice.set(true, false); // hands-free from the start
            });
        }
    };
})();

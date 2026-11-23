"""JARVIS-MARK5 - start with run_jarvis.bat (or: venv\\Scripts\\python jarvis.py)."""
import html
import os
import re
import sys
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import logging  # noqa: E402
from logging.handlers import RotatingFileHandler  # noqa: E402

import eel  # noqa: E402

from backend.core import config, reminders, voice  # noqa: E402
from backend.core.brain import Brain  # noqa: E402
from backend.core.voice import speak  # noqa: E402

# jarvis.log records what JARVIS did and how long each step took (send it along when reporting a problem).
_handler = RotatingFileHandler(os.path.join(ROOT, "jarvis.log"), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.getLogger("jarvis").addHandler(_handler)
logging.getLogger("jarvis").setLevel(logging.INFO)
log = logging.getLogger("jarvis")
STOP_WORDS = {"stop", "cancel", "quiet", "enough", "silence", "pause", "shut", "nevermind"}

_state_lock = threading.Lock()
_base_state = "Available..."   # set by the page: "Available..." or "Listening..."
_activity = None               # set while working: "Thinking...", "Speaking...", ...
_startup_error = None
_busy = threading.Event()
_mute_reply = threading.Event()  # "Jarvis, stop" said while thinking: show the reply but don't speak it
_sent_count = {}               # messages already delivered to each page instance
_awaiting_until = 0.0          # after "Jarvis" alone, the next voice phrase until this time is a command
THEMES = [  # (id, name shown in Settings, page inside web/)
    ("hud", "Iron Man HUD", "themes/hud.html"),
    ("chat", "Chat app", "themes/chat.html"),
    ("orb", "Minimal orb", "themes/orb.html"),
    ("terminal", "Terminal", "themes/terminal.html"),
    ("classic", "Classic", "home.html"),
]
WAKE_ALIASES = {"jarvis": {"jarvis", "javis", "jarvi", "jervis", "jarves", "jarviss"}}

brain = Brain(on_status=lambda s: _set_activity(s))


def _set_activity(text):
    global _activity
    with _state_lock:
        _activity = text


def _translate_to_english(text: str) -> str:
    lang = (brain.cfg.get("INPUT_LANGUAGE") or "en").lower()
    if lang.startswith("en"):
        return text
    try:
        import mtranslate
        return mtranslate.translate(text, "en", "auto")
    except Exception:
        return text


def _process(text: str) -> None:
    _mute_reply.clear()
    try:
        if _startup_error:
            brain.add_message("user", text)
            brain.add_message("assistant", _startup_error)
            return
        reply = brain.handle(_translate_to_english(text))
        print(f"\n{brain.cfg.get('ASSISTANT_NAME', 'JARVIS')} >> {reply}\n")
        if _mute_reply.is_set():
            return
        _set_activity("Speaking...")
        speak(reply, brain.cfg.get("VOICE") or "en-GB-RyanNeural")
    except Exception:
        traceback.print_exc()
    finally:
        _set_activity(None)
        _busy.clear()


def _wake_words():
    name = (brain.cfg.get("ASSISTANT_NAME") or "JARVIS").strip().lower()
    return WAKE_ALIASES.get(name, {name})


def _extract_command(text: str):
    """Returns (heard_wake_word, command). 'Jarvis, open notepad' -> (True, 'open notepad');
    'open notepad Jarvis' -> (True, 'open notepad'); 'Jarvis' -> (True, '')."""
    words = text.split()
    wake = _wake_words()
    for i, w in enumerate(words):
        if re.sub(r"[^a-z]", "", w.lower()) in wake:
            after = " ".join(words[i + 1:]).strip(" ,.!?")
            before = " ".join(words[:i]).strip(" ,.!?")
            before = re.sub(r"^(hey|hi|ok|okay|yo)$", "", before, flags=re.I).strip()
            return True, after or before
    return False, text


def _acknowledge():
    """User said just 'Jarvis': answer and wait a few seconds for the command."""
    global _awaiting_until
    try:
        _set_activity("Yes?")
        speak("Yes?", brain.cfg.get("VOICE") or "en-GB-RyanNeural")
    finally:
        _awaiting_until = time.time() + 8
        _set_activity(None)
        _busy.clear()


# ---------------- functions called from the web page ----------------
@eel.expose
def js_mic(transcription, from_voice=False):
    """Voice or typed input from the page. Input that arrives while JARVIS is busy/speaking is ignored
    (this also stops JARVIS from hearing its own voice). Voice input must contain the wake word
    ("Jarvis") unless REQUIRE_WAKE_WORD is false in config/config.json."""
    global _awaiting_until
    text = (transcription or "").strip()
    if not text:
        return False
    if _busy.is_set():
        # While busy, only "Jarvis, stop" gets through: it interrupts the voice.
        if from_voice:
            heard, command = _extract_command(text)
            words = set(re.sub(r"[^a-z ]", " ", command.lower()).split())
            if heard and words & STOP_WORDS:
                _mute_reply.set()
                voice.stop()
                log.info("speech interrupted by user")
                return True
        return False
    if from_voice and brain.cfg.get("REQUIRE_WAKE_WORD", True):
        heard, command = _extract_command(text)
        if not heard:
            if time.time() > _awaiting_until:
                print(f"(ignored, no wake word): {text}")
                return False
            command = text
        _awaiting_until = 0.0
        if not command:
            _busy.set()
            threading.Thread(target=_acknowledge, daemon=True).start()
            return True
        text = command
    _busy.set()
    print(f"\nYou >> {text}")
    threading.Thread(target=_process, args=(text,), daemon=True).start()
    return True


@eel.expose
def js_state(stat=None):
    global _base_state
    with _state_lock:
        if stat in ("Available...", "Listening..."):
            _base_state = stat
        if _activity:
            return _activity
        if _base_state == "Listening..." and brain.cfg.get("REQUIRE_WAKE_WORD", True):
            if time.time() < _awaiting_until:
                return "Listening for your command..."
            name = (brain.cfg.get("ASSISTANT_NAME") or "JARVIS").strip().title()
            return f'Listening - say "{name}..."'
        return _base_state


@eel.expose
def js_messages(page_id="default"):
    """Returns chat lines the page hasn't shown yet (HTML-escaped)."""
    history = brain.recent(200)
    start = _sent_count.get(page_id, 0)
    if start > len(history):
        start = 0
    _sent_count[page_id] = len(history)
    names = {"assistant": brain.cfg.get("ASSISTANT_NAME", "JARVIS"), "user": brain.cfg.get("USER_NAME", "Sir")}
    out = []
    for m in history[start:]:
        cls = "Assistant" if m["role"] == "assistant" else "User"
        body = html.escape(m["content"]).replace("\n", "<br>")
        out.append({"role": m["role"], "cls": cls, "name": html.escape(names[m["role"]]), "text": body})
    return out


@eel.expose
def js_language():
    return str(brain.cfg.get("INPUT_LANGUAGE") or "en-US")


@eel.expose
def js_assistantname():
    return str(brain.cfg.get("ASSISTANT_NAME") or "JARVIS")


@eel.expose
def js_getsettings():
    c = config.load()
    key = c.get("GROQ_API") or ""
    return {"groq_set": bool(key), "groq_hint": ("..." + key[-4:]) if len(key) > 8 else "",
            "assistant": c.get("ASSISTANT_NAME", ""), "user": c.get("USER_NAME", ""),
            "language": c.get("INPUT_LANGUAGE", "en-US"), "wake_word": bool(c.get("REQUIRE_WAKE_WORD", True)),
            "theme": _theme_id(c.get("THEME")), "themes": [{"id": t, "name": n, "page": "/" + p} for t, n, p in THEMES],
            "email": c.get("EMAIL_ADDRESS", ""), "email_password_set": bool(c.get("EMAIL_APP_PASSWORD")),
            "country_code": c.get("COUNTRY_CODE", "")}


def _theme_id(theme):
    return theme if any(t == theme for t, _, _ in THEMES) else "hud"


def _theme_page(theme):
    return next(p for t, _, p in THEMES if t == _theme_id(theme))


@eel.expose
def js_savesettings(values):
    """Saves settings from the settings panel shared by all themes. Empty text fields keep their value."""
    global _startup_error
    values = values or {}
    updates = {}
    for field, key in (("groq", "GROQ_API"), ("assistant", "ASSISTANT_NAME"), ("user", "USER_NAME"), ("language", "INPUT_LANGUAGE"),
                       ("email", "EMAIL_ADDRESS"), ("email_password", "EMAIL_APP_PASSWORD"), ("country_code", "COUNTRY_CODE")):
        v = str(values.get(field) or "").strip()
        if v:
            updates[key] = v
    if "wake_word" in values:
        updates["REQUIRE_WAKE_WORD"] = bool(values["wake_word"])
    if values.get("theme"):
        updates["THEME"] = _theme_id(values["theme"])
    brain.cfg = config.save(updates)
    result = {"ok": True, "message": "Settings saved.", "page": "/" + _theme_page(brain.cfg.get("THEME"))}
    if "GROQ_API" in updates or _startup_error:
        try:
            brain.connect()
            _startup_error = None
        except Exception as e:
            _startup_error = str(e)
            result.update(ok=False, message=_startup_error)
    return result


@eel.expose
def js_sysinfo():
    """CPU / memory / battery for the HUD theme."""
    try:
        import psutil
        info = {"cpu": round(psutil.cpu_percent(interval=None)), "ram": round(psutil.virtual_memory().percent)}
        battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        if battery is not None:
            info["battery"] = round(battery.percent)
            info["plugged"] = bool(battery.power_plugged)
        return info
    except Exception:
        return {}


@eel.expose
def js_setvalues(groq_key, assistant_name, user_name, language):
    """Saves settings from the Settings page. Empty fields keep their current value."""
    global _startup_error
    updates = {}
    if groq_key and groq_key.strip():
        updates["GROQ_API"] = groq_key.strip()
    if assistant_name and assistant_name.strip():
        updates["ASSISTANT_NAME"] = assistant_name.strip()
    if user_name and user_name.strip():
        updates["USER_NAME"] = user_name.strip()
    if language and language.strip():
        updates["INPUT_LANGUAGE"] = language.strip()
    brain.cfg = config.save(updates)
    if "GROQ_API" in updates or _startup_error:
        try:
            brain.connect()
            _startup_error = None
        except Exception as e:
            _startup_error = str(e)
            return {"ok": False, "message": _startup_error}
    return {"ok": True, "message": "Settings saved."}


def _choose_browser_mode():
    try:
        import eel.chrome
        if eel.chrome.find_path():
            return "chrome"
    except Exception:
        pass
    return "edge" if sys.platform == "win32" else "default"


def _reminder_due(text: str) -> None:
    """Runs in the reminder thread: shows and speaks the reminder (waits if JARVIS is busy)."""
    for _ in range(120):
        if not _busy.is_set():
            break
        time.sleep(1)
    _busy.set()
    try:
        message = f"Reminder: {text}"
        brain.add_message("assistant", message)
        _set_activity("Speaking...")
        speak(message, brain.cfg.get("VOICE") or "en-GB-RyanNeural")
    finally:
        _set_activity(None)
        _busy.clear()


def main():
    global _startup_error
    log.info("JARVIS starting")
    try:
        brain.connect()
    except Exception as e:
        _startup_error = str(e)
        print(f"[jarvis] {e}")
    reminders.start_worker(_reminder_due)

    port = int(os.environ.get("JARVIS_PORT", "44444"))
    eel.init(os.path.join(ROOT, "web"))
    mode = os.environ.get("JARVIS_BROWSER") or _choose_browser_mode()
    if mode == "none":
        mode = False  # server only; open the printed address yourself
    page = _theme_page(brain.cfg.get("THEME"))
    print(f"[jarvis] Opening the JARVIS window ({mode or 'no browser'}) on http://localhost:{port}/{page}")
    eel.start(page, mode=mode, port=port, size=(1440, 900), block=True)


if __name__ == "__main__":
    main()

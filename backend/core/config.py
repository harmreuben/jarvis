"""Loads and saves JARVIS settings from config/config.json."""
import json
import os
import threading

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(ROOT_DIR, "config", "config.json")
CHATLOG_PATH = os.path.join(ROOT_DIR, "ChatLog.json")

DEFAULTS = {
    "GROQ_API": "",
    "LLM_MODEL": "",        # empty = pick the best available Groq model automatically
    "VISION_MODEL": "",     # empty = pick automatically
    "USER_NAME": "Sir",
    "ASSISTANT_NAME": "JARVIS",
    "INPUT_LANGUAGE": "en-US",
    "VOICE": "en-GB-RyanNeural",
    "OCR_LINK": "",
    "REQUIRE_WAKE_WORD": True,
    "THEME": "hud",
    "EMAIL_ADDRESS": "",        # for reading/sending email (Gmail, Yahoo, iCloud, Zoho)
    "EMAIL_APP_PASSWORD": "",   # an app password, not your normal password
    "COUNTRY_CODE": "",         # phone country calling code for WhatsApp numbers starting with 0, e.g. 254             # hud, chat, orb, terminal or classic - change it in Settings  # voice commands must contain the assistant's name ("Jarvis, open notepad")
}

_lock = threading.Lock()


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            data.update({k: v for k, v in stored.items() if v is not None})
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as e:
        raise SystemExit(f"config/config.json is not valid JSON ({e}). Fix or delete it, then start JARVIS again.")
    return data


def save(updates: dict) -> dict:
    with _lock:
        data = load()
        data.update(updates)
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        os.replace(tmp, CONFIG_PATH)
        return data

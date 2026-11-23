"""AI providers JARVIS can use. All of them speak the OpenAI chat-completions API, so one client library covers them.

- Google Gemini  (free key: https://aistudio.google.com/apikey)  - fast, tools and images
- Groq           (free key: https://console.groq.com/keys)
- Ollama         (free, open-source models running on this PC: https://ollama.com)

JARVIS uses every provider that is set up, best first, and moves to the next when one fails or hits its limit."""
import os
import re
from dataclasses import dataclass

import openai

PROVIDERS = {
    "gemini": {"name": "Google Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai/", "key": "GEMINI_API_KEY"},
    "groq": {"name": "Groq", "url": "https://api.groq.com/openai/v1", "key": "GROQ_API"},
    "ollama": {"name": "Ollama (this PC)", "url": "http://localhost:11434/v1", "key": None},
}
ORDER = ["gemini", "groq", "ollama"]

GROQ_CHAT = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
GROQ_SKIP = ("whisper", "guard", "tts", "playai", "orpheus", "distil", "compound", "allam", "llama-4", "vision")
OLLAMA_CHAT = ("qwen3", "llama3.1", "llama3.2", "qwen2.5", "mistral-nemo", "mistral-small", "llama3.3", "gpt-oss", "command-r")
OLLAMA_VISION = ("gemma3", "qwen2.5vl", "llama3.2-vision", "llava", "minicpm-v", "llama4")
GEMINI_SKIP = ("image", "tts", "audio", "live", "embedding", "native", "computer", "robotics", "thinking", "8b", "learnlm")
GEMINI_FALLBACK = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]


@dataclass
class Target:
    provider: str
    model: str
    client: object

    @property
    def label(self):
        return f"{PROVIDERS[self.provider]['name']}: {self.model}"


def _url(pid, cfg):
    env = os.environ.get(f"JARVIS_{pid.upper()}_BASE_URL")  # used by tests
    if env:
        return env
    if pid == "ollama" and cfg.get("OLLAMA_URL"):
        return cfg["OLLAMA_URL"]
    return PROVIDERS[pid]["url"]


def _gemini_rank(m):
    v = re.search(r"gemini-(\d+(?:\.\d+)?)", m)
    return (-(float(v.group(1)) if v else 0), "preview" in m or "exp" in m, "lite" in m, len(m))


def _choose(pid, ids, configured):
    """Returns (chat models best-first, vision models best-first) for one provider."""
    chat, vision = [], []
    if configured and configured in ids:
        chat.append(configured)
    if pid == "gemini":
        flash = sorted([m for m in ids if m.startswith("gemini-") and "flash" in m and not any(x in m for x in GEMINI_SKIP)],
                       key=_gemini_rank)
        chat += flash[:3]
        vision = flash[:2]  # Gemini models understand images
    elif pid == "groq":
        chat += [m for m in GROQ_CHAT if m in ids]
        chat += [m for m in ids if m not in chat and not any(x in m.lower() for x in GROQ_SKIP)][:1]
        vision = [m for m in ids if "llama-4" in m or "vision" in m]
    else:  # ollama: whatever the user has pulled
        chat += [m for p in OLLAMA_CHAT for m in ids if m.startswith(p)]
        vision = [m for p in OLLAMA_VISION for m in ids if m.startswith(p)]
    seen, ordered = set(), []
    for m in chat:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered[:4], vision[:2]


def discover(cfg):
    """Connects to every configured provider. Returns (chat targets, vision targets, notes)."""
    primary = (cfg.get("AI_PROVIDER") or "auto").lower()
    order = ([primary] if primary in PROVIDERS else []) + [p for p in ORDER if p != primary]
    chat, vision, notes = [], [], []
    for pid in order:
        info = PROVIDERS[pid]
        key = (cfg.get(info["key"]) or "").strip() if info["key"] else "ollama"
        if not key:
            continue
        if pid == "ollama" and primary != "ollama" and not cfg.get("USE_OLLAMA"):
            continue
        client = openai.OpenAI(api_key=key, base_url=_url(pid, cfg), timeout=60 if pid != "ollama" else 180, max_retries=1)
        try:
            ids = [m.id.split("/", 1)[1] if m.id.startswith("models/") else m.id
                   for m in client.with_options(timeout=15).models.list().data]
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            notes.append(f"{info['name']}: the API key was rejected")
            continue
        except openai.BadRequestError as e:
            if "key" in str(e).lower():
                notes.append(f"{info['name']}: the API key was rejected")
                continue
            ids = GEMINI_FALLBACK if pid == "gemini" else []
        except openai.APIConnectionError:
            notes.append(f"{info['name']}: can't connect" + (" (is Ollama running?)" if pid == "ollama" else ""))
            continue
        except Exception as e:
            if pid != "gemini":
                notes.append(f"{info['name']}: {e}")
                continue
            ids = GEMINI_FALLBACK  # model list unavailable: use well-known names
        configured = cfg.get("LLM_MODEL") if pid == order[0] else None
        c, v = _choose(pid, ids, configured)
        if not c:
            notes.append(f"{info['name']}: no suitable chat model" + (" - run 'ollama pull qwen3'" if pid == "ollama" else ""))
        chat += [Target(pid, m, client) for m in c]
        vision += [Target(pid, m, client) for m in v]
    return chat, vision, notes

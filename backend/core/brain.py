"""JARVIS brain: one Groq call per request. The model either answers directly or calls tools (backend/core/tools.py)."""
import json
import logging
import os
import threading
import time
from datetime import datetime

import groq
from groq import Groq, AuthenticationError

from backend.core import actions, config, tools
from backend.core.presentation import SLIDE_PROMPT, build_pptx

log = logging.getLogger("jarvis")

LLM_PREFERENCES = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
]
VISION_PREFERENCES = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
]
NOT_CHAT_MODELS = ("whisper", "guard", "tts", "playai", "orpheus", "prompt-guard", "distil", "llama-4", "compound", "allam")

TASK_PROMPT = """Write a complete Python 3 script that performs this task on a Windows 11 PC.
Rules:
- Only use the standard library and these installed packages: pyautogui, pyperclip, requests, beautifulsoup4 (bs4), pandas, openpyxl, PyMuPDF (fitz), python-pptx (pptx), python-docx (docx), Pillow (PIL), opencv-python (cv2), numpy, psutil, send2trash.
- Use absolute paths built from os.path.expanduser("~") for user folders (Desktop, Documents, Downloads, ...).
- Never delete files permanently; use send2trash for deleting.
- print() a short, human-friendly summary of what was done at the end.
- Reply with ONLY the code inside one ```python code block."""

MAX_TOOL_ROUNDS = 4


class Brain:
    def __init__(self, on_status=None):
        self.cfg = config.load()
        self.on_status = on_status or (lambda s: None)
        self.client = None
        self.llm_model = None
        self.fallback_models = []
        self.vision_model = None
        self.history = self._load_history()
        self._history_lock = threading.Lock()
        self._limited_until = {}  # model -> time when its rate limit should be over

    # ---------- setup ----------
    def connect(self) -> None:
        """Validates the Groq key and picks models that are currently available on the account."""
        key = (self.cfg.get("GROQ_API") or "").strip()
        if not key:
            raise RuntimeError("No Groq API key set. Open Settings in JARVIS (or run setup again) and paste your key from console.groq.com/keys.")
        self.client = Groq(api_key=key, timeout=45, max_retries=1)
        try:
            available = [m.id for m in self.client.models.list().data]
        except AuthenticationError:
            raise RuntimeError("Your Groq API key was rejected. Create a new one at console.groq.com/keys and save it in Settings.")
        self.llm_model = self._pick(self.cfg.get("LLM_MODEL"), LLM_PREFERENCES, available, vision=False)
        self.vision_model = self._pick(self.cfg.get("VISION_MODEL"), VISION_PREFERENCES, available, vision=True)
        if not self.llm_model:
            raise RuntimeError("No usable chat model found on your Groq account.")
        self.fallback_models = [m for m in LLM_PREFERENCES if m in available and m != self.llm_model]
        print(f"[brain] chat model: {self.llm_model} (fallbacks: {', '.join(self.fallback_models) or 'none'}) | "
              f"vision model: {self.vision_model or 'none available'}")

    @staticmethod
    def _pick(configured, preferences, available, vision):
        if configured and configured in available:
            return configured
        for m in preferences:
            if m in available:
                return m
        if vision:
            return next((m for m in available if "llama-4" in m or "vision" in m), None)
        return next((m for m in available if not any(x in m.lower() for x in NOT_CHAT_MODELS)), None)

    # ---------- chat history (shown in the GUI) ----------
    def _load_history(self):
        try:
            with open(config.CHATLOG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return [m for m in data if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def add_message(self, role: str, content: str) -> None:
        with self._history_lock:
            self.history.append({"role": role, "content": content})
            self.history = self.history[-200:]
            tmp = config.CHATLOG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
            os.replace(tmp, config.CHATLOG_PATH)

    def recent(self, n: int):
        with self._history_lock:
            return [dict(m) for m in self.history[-n:]]

    # ---------- model calls ----------
    def _system(self):
        name, user = self.cfg.get("ASSISTANT_NAME", "JARVIS"), self.cfg.get("USER_NAME", "Sir")
        return (f"You are {name}, a capable, witty AI assistant inspired by Tony Stark's JARVIS, running on {user}'s Windows 11 PC "
                f"with access to their apps, files, browser, contacts, WhatsApp, email and reminders through your tools. "
                f"Address the user as {user}. Use tools whenever the request needs the PC, the internet, files, messages or reminders; "
                f"answer directly (no tool) for conversation and general knowledge. For multi-step requests call the tools in order "
                f"(e.g. open notepad, then type). Never invent file paths, phone numbers or email addresses: search or ask. "
                f"Replies are read aloud: keep them short and natural (1-3 sentences) unless asked for detail. No markdown tables. "
                f"Current local date and time: {datetime.now():%A %d %B %Y, %H:%M}.")

    def _create(self, **kwargs):
        """chat.completions.create with automatic fallback to other models when one is rate-limited."""
        models = [kwargs.pop("model", None) or self.llm_model] + [m for m in self.fallback_models]
        last_error = None
        for m in models:
            if self._limited_until.get(m, 0) > time.time():
                continue
            try:
                t0 = time.time()
                resp = self.client.chat.completions.create(model=m, **kwargs)
                log.info("groq %s %.2fs", m, time.time() - t0)
                return resp
            except groq.RateLimitError as e:
                wait = 60.0
                try:
                    wait = float(e.response.headers.get("retry-after", 60))
                except Exception:
                    pass
                self._limited_until[m] = time.time() + wait
                log.warning("rate limited on %s for %.0fs, trying next model", m, wait)
                last_error = e
            except groq.APIConnectionError as e:
                raise RuntimeError("I can't reach the Groq servers. Check your internet connection.") from e
        raise RuntimeError("Groq's free limit is used up on all models right now. Try again in a little while "
                           "(limits reset during the day).") from last_error

    def complete(self, messages, model=None, max_tokens=1024, temperature=0.6) -> str:
        resp = self._create(model=model, messages=messages, max_tokens=max_tokens, temperature=temperature)
        return (resp.choices[0].message.content or "").strip()

    def vision(self, question: str, data_url: str) -> str:
        if not self.vision_model:
            return "No image-capable model is available on your Groq account right now."
        messages = [{"role": "system", "content": self._system()},
                    {"role": "user", "content": [{"type": "text", "text": question},
                                                 {"type": "image_url", "image_url": {"url": data_url}}]}]
        resp = self.client.chat.completions.create(model=self.vision_model, messages=messages, max_tokens=500)
        return (resp.choices[0].message.content or "").strip()

    # ---------- main entry ----------
    def handle(self, query: str) -> str:
        t0 = time.time()
        self.add_message("user", query)
        try:
            self.on_status("Thinking...")
            reply = self._agent(query)
        except Exception as e:
            log.exception("request failed")
            reply = str(e) if isinstance(e, (RuntimeError, ValueError, FileNotFoundError)) else f"Sorry, something went wrong: {e}"
        reply = (reply or "Done.").strip()
        self.add_message("assistant", reply)
        log.info("request done in %.2fs: %r", time.time() - t0, query[:80])
        return reply

    def _agent(self, query: str) -> str:
        history = []
        for m in self.recent(9)[:-1]:  # earlier turns, trimmed to keep requests small and fast
            history.append({"role": m["role"], "content": m["content"][:800]})
        messages = [{"role": "system", "content": self._system()}] + history + [{"role": "user", "content": query}]
        spoken = []
        for _round in range(MAX_TOOL_ROUNDS):
            try:
                resp = self._create(messages=messages, tools=tools.TOOLS, tool_choice="auto",
                                    max_tokens=1024, temperature=0.3)
            except groq.BadRequestError as e:
                # The model produced a malformed tool call: retry once as plain chat.
                log.warning("tool call failed (%s); answering without tools", e)
                return self.complete(messages[:1] + history + [{"role": "user", "content": query}])
            msg = resp.choices[0].message
            calls = msg.tool_calls or []
            if not calls:
                text = (msg.content or "").strip()
                return " ".join(spoken + [text]).strip() if spoken else text
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [{"id": c.id, "type": "function",
                                             "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                            for c in calls]})
            needs_answer = False
            for i, c in enumerate(calls):
                try:
                    args = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                log.info("tool %s %s", c.function.name, json.dumps(args, ensure_ascii=False)[:300])
                print(f"[brain] tool {c.function.name} {args}")
                try:
                    result, info = tools.run(self, c.function.name, args)
                except Exception as e:
                    log.exception("tool %s failed", c.function.name)
                    result, info = f"Error: {e}", True
                if not info:
                    spoken.append(result)
                needs_answer = needs_answer or info
                messages.append({"role": "tool", "tool_call_id": c.id, "content": str(result)[:12000]})
                if i < len(calls) - 1:
                    tools.pause_between(c.function.name, args)
            if not needs_answer:
                return " ".join(spoken)  # simple actions: no second AI call, reply immediately
            self.on_status("Thinking...")
        return " ".join(spoken) or "I couldn't finish that."

    # ---------- bigger jobs used by tools ----------
    def make_presentation(self, topic: str) -> str:
        self.on_status("Writing slides...")
        text = self.complete([{"role": "system", "content": SLIDE_PROMPT},
                              {"role": "user", "content": f"Topic: {topic}"}], max_tokens=3000)
        path = build_pptx(topic, text)
        if actions.IS_WINDOWS:
            os.startfile(path)
        return f"Your presentation is ready and saved to {path}"

    def run_task(self, task: str) -> str:
        from backend.modules.filter import filter_python
        self.on_status("Writing code...")
        answer = self.complete([{"role": "system", "content": TASK_PROMPT},
                                {"role": "user", "content": task}], max_tokens=2500, temperature=0.2)
        code = filter_python(answer) or (answer if answer.lstrip().startswith(("import", "from", "#")) else None)
        if not code:
            return "I couldn't work out how to do that one."
        self.on_status("Waiting for your OK...")
        ran, rc, output = actions.run_python_task(code)
        if not ran:
            return "Okay, I won't run it."
        if rc == 0:
            return output[-800:] if output else "Task completed."
        return "The task failed: " + (output[-600:] or f"exit code {rc}")

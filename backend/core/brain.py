"""JARVIS brain: one AI call per request. The model either answers directly or calls tools (backend/core/tools.py).
Works with Google Gemini, Groq and Ollama (backend/core/providers.py), switching automatically when one fails."""
import json
import logging
import os
import threading
import time
from datetime import datetime

import openai

from backend.core import actions, config, providers, tools
from backend.core.presentation import SLIDE_PROMPT, build_pptx

log = logging.getLogger("jarvis")

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
        self.targets = []         # chat models, best first, across all providers
        self.vision_targets = []  # image-capable models
        self.notes = []
        self.history = self._load_history()
        self._history_lock = threading.Lock()
        self._limited_until = {}  # model -> time when its rate limit should be over

    # ---------- setup ----------
    def connect(self) -> None:
        """Connects to every configured AI provider and picks the models available on each account."""
        self.cfg = config.load()
        if not any((self.cfg.get(k) or "").strip() for k in ("GEMINI_API_KEY", "GROQ_API")) and \
                (self.cfg.get("AI_PROVIDER") != "ollama" and not self.cfg.get("USE_OLLAMA")):
            raise RuntimeError("No AI key set. Open Settings and paste a free Google Gemini key (aistudio.google.com/apikey) "
                               "or a Groq key (console.groq.com/keys).")
        self.targets, self.vision_targets, self.notes = providers.discover(self.cfg)
        for n in self.notes:
            print(f"[brain] {n}")
            log.warning(n)
        if not self.targets:
            raise RuntimeError("I couldn't connect to any AI provider: " + "; ".join(self.notes or ["unknown error"]) +
                               ". Check your keys in Settings and your internet connection.")
        self._limited_until.clear()
        print(f"[brain] chat: {', '.join(t.label for t in self.targets)} | "
              f"vision: {', '.join(t.label for t in self.vision_targets) or 'none available'}")

    @property
    def llm_model(self):
        return self.targets[0].model if self.targets else None

    @property
    def vision_model(self):
        return self.vision_targets[0].model if self.vision_targets else None

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

    def _create(self, targets=None, **kwargs):
        """chat.completions.create on the best available model; moves on to the next model/provider on failure."""
        targets = self.targets if targets is None else targets
        last_error, bad_request = None, None
        for t in targets:
            key = (t.provider, t.model)
            if self._limited_until.get(key, 0) > time.time() or self._limited_until.get(t.provider, 0) > time.time():
                continue
            try:
                t0 = time.time()
                resp = t.client.chat.completions.create(model=t.model, **kwargs)
                log.info("%s %.2fs", t.label, time.time() - t0)
                return resp
            except openai.RateLimitError as e:
                wait = 60.0
                try:
                    wait = float(e.response.headers.get("retry-after", 60))
                except Exception:
                    pass
                self._limited_until[key] = time.time() + min(wait, 3600)
                log.warning("%s rate limited for %.0fs; trying the next model", t.label, wait)
                last_error = e
            except (openai.APIConnectionError, openai.APITimeoutError) as e:
                self._limited_until[t.provider] = time.time() + 30
                log.warning("%s unreachable: %s", t.label, e)
                last_error = e
            except (openai.AuthenticationError, openai.PermissionDeniedError) as e:
                self._limited_until[t.provider] = time.time() + 600
                log.warning("%s rejected the key: %s", t.label, e)
                last_error = e
            except openai.NotFoundError as e:
                self._limited_until[key] = time.time() + 3600
                log.warning("%s model not found: %s", t.label, e)
                last_error = e
            except openai.BadRequestError as e:
                log.warning("%s bad request: %s", t.label, e)
                bad_request = bad_request or e
            except openai.APIStatusError as e:  # 5xx and other server-side trouble
                self._limited_until[key] = time.time() + 20
                log.warning("%s server error: %s", t.label, e)
                last_error = e
        if bad_request is not None:
            raise bad_request
        if isinstance(last_error, openai.RateLimitError):
            raise RuntimeError("The free AI limits are used up on all your providers right now. Try again in a little "
                               "while, or add another provider's key in Settings.") from last_error
        if isinstance(last_error, (openai.APIConnectionError, openai.APITimeoutError)):
            raise RuntimeError("I can't reach the AI service. Check your internet connection.") from last_error
        raise RuntimeError("No AI model is available right now" + (f" ({last_error})" if last_error else "") +
                           ". Check your keys in Settings.") from last_error

    @staticmethod
    def _text(resp) -> str:
        return (resp.choices[0].message.content or "").strip()

    def complete(self, messages, max_tokens=2048, temperature=0.6, targets=None) -> str:
        resp = self._create(targets=targets, messages=messages, max_tokens=max_tokens, temperature=temperature)
        text = self._text(resp)
        if not text and resp.choices[0].finish_reason == "length":
            # "Thinking" models can spend the whole budget reasoning; give them room and ask again.
            resp = self._create(targets=targets, messages=messages, max_tokens=min(max(max_tokens * 4, 4096), 8192),
                                temperature=temperature)
            text = self._text(resp)
        return text

    def vision(self, question: str, data_url: str) -> str:
        if not self.vision_targets:
            return ("None of your AI providers can look at images right now. Add a free Google Gemini key in Settings "
                    "to use the screen and camera features.")
        messages = [{"role": "system", "content": self._system()},
                    {"role": "user", "content": [{"type": "text", "text": question},
                                                 {"type": "image_url", "image_url": {"url": data_url}}]}]
        return self.complete(messages, max_tokens=1500, targets=self.vision_targets) or "I couldn't make out anything."

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
                                    max_tokens=2048, temperature=0.3)
                if not resp.choices[0].message.tool_calls and not self._text(resp) and resp.choices[0].finish_reason == "length":
                    resp = self._create(messages=messages, tools=tools.TOOLS, tool_choice="auto",
                                        max_tokens=8192, temperature=0.3)
            except openai.BadRequestError as e:
                # The model produced a malformed tool call: retry once as plain chat.
                log.warning("tool call failed (%s); answering without tools", e)
                return self.complete(messages[:1] + history + [{"role": "user", "content": query}])
            msg = resp.choices[0].message
            calls = msg.tool_calls or []
            if not calls:
                text = (msg.content or "").strip() or ("" if spoken else "Sorry, I didn't get an answer that time. Please try again.")
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

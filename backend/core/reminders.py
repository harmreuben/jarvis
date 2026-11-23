"""Reminders and timers. Saved to config/reminders.json so they survive a restart."""
import json
import os
import threading
import time
from datetime import datetime, timedelta

from backend.core import config

PATH = os.path.join(config.ROOT_DIR, "config", "reminders.json")
_lock = threading.Lock()


def _load():
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(items):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    os.replace(tmp, PATH)


def _parse_when(when: str) -> datetime:
    when = (when or "").strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M"):
        try:
            dt = datetime.strptime(when[:19], fmt)
            if fmt == "%H:%M":
                now = datetime.now()
                dt = now.replace(hour=dt.hour, minute=dt.minute, second=0, microsecond=0)
                if dt <= now:
                    dt += timedelta(days=1)
            return dt
        except ValueError:
            continue
    raise ValueError(f"I couldn't understand the time '{when}'.")


def add(text: str, when: str = "", minutes: float = 0) -> str:
    if minutes:
        due = datetime.now() + timedelta(minutes=float(minutes))
    else:
        due = _parse_when(when)
    if due <= datetime.now():
        return "That time has already passed."
    with _lock:
        items = _load()
        items.append({"text": text.strip() or "Reminder", "due": due.isoformat(timespec="seconds")})
        _save(items)
    day = "today" if due.date() == datetime.now().date() else "tomorrow" if due.date() == (datetime.now() + timedelta(days=1)).date() else due.strftime("%A %d %B")
    return f"Okay, I'll remind you to {text} at {due:%I:%M %p} {day}." if not minutes else f"Timer set for {_fmt_minutes(minutes)}."


def _fmt_minutes(m: float) -> str:
    m = float(m)
    if m < 1:
        return f"{round(m * 60)} seconds"
    if m < 60:
        return f"{m:g} minute{'s' if m != 1 else ''}"
    return f"{m / 60:g} hour{'s' if m != 60 else ''}"


def list_all() -> str:
    items = sorted(_load(), key=lambda r: r["due"])
    if not items:
        return "You have no reminders."
    return "\n".join(f"- {datetime.fromisoformat(r['due']):%a %d %b %I:%M %p}: {r['text']}" for r in items)


def cancel(text: str) -> str:
    with _lock:
        items = _load()
        keep = [r for r in items if text.lower() not in r["text"].lower()] if text else []
        removed = len(items) - len(keep)
        _save(keep)
    return f"Cancelled {removed} reminder(s)." if removed else f"No reminder matched '{text}'."


def start_worker(on_due):
    """Calls on_due(text) for every reminder that becomes due. Runs in a background thread."""
    def loop():
        while True:
            try:
                now = datetime.now()
                with _lock:
                    items = _load()
                    due = [r for r in items if datetime.fromisoformat(r["due"]) <= now]
                    if due:
                        _save([r for r in items if r not in due])
                for r in due:
                    late = now - datetime.fromisoformat(r["due"])
                    on_due(r["text"] + (" (this was due while JARVIS was off)" if late > timedelta(minutes=5) else ""))
            except Exception as e:
                print(f"[reminders] {e}")
            time.sleep(10)
    threading.Thread(target=loop, daemon=True, name="reminders").start()

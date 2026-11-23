"""Tool definitions JARVIS's AI can call, and the code that runs them.

Each tool returns (text, needs_answer). needs_answer=False means the text is spoken directly (fast, one AI call);
True means the text is information the AI turns into an answer (search results, file contents, ...)."""
import os
import time

from backend.core import actions, comms, files, reminders, web


def _fn(name, description, props, required=()):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": props, "required": list(required)}}}


def _enum(*values, desc=""):
    d = {"type": "string", "enum": list(values)}
    if desc:
        d["description"] = desc
    return d


S = {"type": "string"}

TOOLS = [
    _fn("web", "Internet: search for current info, open a URL, Google/YouTube, read the page open in the browser or a URL, download a file.",
        {"action": _enum("search", "open_url", "google", "youtube", "read_current_page", "read_url", "download"),
         "query": {"type": "string", "description": "search terms, or the URL"}}, ["action"]),
    _fn("apps", "Open, close, switch to, minimize or maximize apps/windows on the PC.",
        {"action": _enum("open", "close", "switch", "minimize", "maximize", "minimize_all", "next_window"),
         "name": {"type": "string", "description": "app or window name, e.g. 'spotify', 'chrome', 'visual studio code'"}}, ["action"]),
    _fn("keyboard", "Type text into the active window, press keys/shortcuts (e.g. 'ctrl+s', 'enter', 'alt+f4'), scroll, or click text visible on screen.",
        {"action": _enum("type", "press", "scroll_up", "scroll_down", "click_text"), "text": S}, ["action"]),
    _fn("media", "Media playback and speaker volume.",
        {"action": _enum("play_pause", "next", "previous", "stop", "mute", "volume_up", "volume_down", "volume_set"),
         "level": {"type": "number", "description": "0-100 for volume_set"}}, ["action"]),
    _fn("system", "Windows: screen brightness, dark/light mode, taskbar position, lock/sleep/shutdown/restart/sign out, "
                  "open a Settings page (wifi, bluetooth, display, sound, network, battery, apps, updates, storage, ...), or get system info "
                  "(battery, CPU, memory, disk space, IP).",
        {"action": _enum("brightness_set", "brightness_up", "brightness_down", "dark_mode", "light_mode", "taskbar_left",
                         "taskbar_center", "lock", "sleep", "shutdown", "restart", "sign_out", "cancel_shutdown",
                         "open_settings_page", "info"),
         "value": {"type": "string", "description": "brightness 0-100, or the settings page name"}}, ["action"]),
    _fn("screen", "Take a screenshot, or look at the screen / through the webcam to answer a question about what is visible.",
        {"action": _enum("screenshot", "look_screen", "look_camera"), "question": S}, ["action"]),
    _fn("files", "The user's files and folders (Desktop, Documents, Downloads, Pictures, Music, Videos, OneDrive). "
                 "find / open / read (txt, pdf, docx, xlsx, pptx...) / list a folder / create_folder / write a text file or note / move / copy / rename / delete (to Recycle Bin). "
                 "'path' can be a file name to search for, a folder like 'downloads', or a full path.",
        {"action": _enum("find", "open", "read", "list", "create_folder", "write", "move", "copy", "rename", "delete"),
         "path": S, "destination": {"type": "string", "description": "target folder for move/copy/create_folder/write, or the new name for rename"},
         "content": {"type": "string", "description": "text for write"},
         "file_type": _enum("pdf", "word", "excel", "powerpoint", "image", "video", "music", "text", "zip", "program")},
        ["action"]),
    _fn("contacts", "Saved contacts (names with phone numbers and emails) used for WhatsApp and email.",
        {"action": _enum("add", "list", "remove"), "name": S, "phone": {"type": "string", "description": "with country code if known, e.g. +254712345678"},
         "email": S}, ["action"]),
    _fn("send_message", "Send a WhatsApp message or an email to a contact name, phone number or email address. The user confirms before sending.",
        {"channel": _enum("whatsapp", "email"), "to": S, "message": S, "subject": {"type": "string", "description": "email subject"}},
        ["channel", "to", "message"]),
    _fn("check_email", "Read the latest emails in the user's inbox.",
        {"count": {"type": "integer"}, "unread_only": {"type": "boolean"}}),
    _fn("reminders", "Reminders and timers. For 'set', give 'when' as a local date-time YYYY-MM-DDTHH:MM. For 'timer' give minutes.",
        {"action": _enum("set", "timer", "list", "cancel"), "text": S, "when": S, "minutes": {"type": "number"}}, ["action"]),
    _fn("create_powerpoint", "Create a PowerPoint presentation about a topic.", {"topic": S}, ["topic"]),
    _fn("run_task", "Last resort for computer tasks no other tool can do (bulk file operations, data processing, converting files...). "
                    "Writes and runs a Python script after the user approves it.",
        {"task": {"type": "string", "description": "precise description of the task"}}, ["task"]),
]

INFO = True
DONE = False


def run(brain, name: str, a: dict):
    """Executes one tool call. Returns (text, needs_answer)."""
    act = (a.get("action") or "").strip()
    g = lambda k: str(a.get(k) or "").strip()

    if name == "web":
        q = g("query")
        if act == "search":
            brain.on_status("Searching the web...")
            return web.search(q), INFO
        if act == "open_url":
            return actions.open_website(q), DONE
        if act == "google":
            return web.google(q), DONE
        if act == "youtube":
            return actions.play_youtube(q), DONE
        if act == "read_current_page":
            brain.on_status("Reading the page...")
            return web.read_current_page(), INFO
        if act == "read_url":
            brain.on_status("Reading the page...")
            return web.page_text(q if q.startswith("http") else "https://" + q), INFO
        if act == "download":
            brain.on_status("Downloading...")
            return web.download(q), DONE

    if name == "apps":
        n = g("name")
        if act == "open":
            return (actions.open_app(n) if n else "Which app?"), DONE
        if act == "close":
            return (actions.close_app(n) if n else "Which app should I close?"), DONE
        return actions.window_control(act, n), DONE

    if name == "keyboard":
        t = a.get("text") or ""
        if act == "type":
            return actions.type_text(t), DONE
        if act == "press":
            return actions.press_keys(t), DONE
        if act in ("scroll_up", "scroll_down"):
            return actions.scroll("up" if act == "scroll_up" else "down"), DONE
        if act == "click_text":
            brain.on_status("Reading the screen...")
            return actions.click_on_screen(t), DONE

    if name == "media":
        return actions.media(act, a.get("level")), DONE

    if name == "system":
        v = g("value")
        if act.startswith("brightness"):
            return actions.brightness({"brightness_up": "up", "brightness_down": "down"}.get(act, "set"), v), DONE
        if act in ("dark_mode", "light_mode", "taskbar_left", "taskbar_center"):
            return actions.system_setting(act), DONE
        if act in ("lock", "sleep", "shutdown", "restart", "sign_out", "cancel_shutdown"):
            return actions.power(act), DONE
        if act == "open_settings_page":
            return actions.open_settings_page(v), DONE
        if act == "info":
            return actions.system_info(), INFO

    if name == "screen":
        if act == "screenshot":
            return f"Screenshot saved to {actions.take_screenshot()}", DONE
        question = g("question") or "Describe what you see."
        if act == "look_camera":
            brain.on_status("Looking...")
            return brain.vision(question, actions.capture_camera_image()), DONE
        brain.on_status("Looking at the screen...")
        return brain.vision(question, actions.capture_screen_image()), DONE

    if name == "files":
        p, dest = g("path"), g("destination")
        if act == "find":
            brain.on_status("Searching your files...")
            return files.describe(files.find(p, folder=dest, file_type=g("file_type"))), INFO
        if act == "open":
            return files.open_path(p), DONE
        if act == "read":
            brain.on_status("Reading the file...")
            return files.read_text(p), INFO
        if act == "list":
            return files.list_folder(p or dest), INFO
        if act == "create_folder":
            return files.create_folder(p, dest), DONE
        if act == "write":
            return files.write_file(p, a.get("content") or "", dest), DONE
        if act in ("move", "copy"):
            return files.move_copy(p, dest, act), DONE
        if act == "rename":
            return files.rename(p, dest), DONE
        if act == "delete":
            return files.delete(p), DONE

    if name == "contacts":
        if act == "add":
            return comms.add_contact(g("name"), g("phone"), g("email")), DONE
        if act == "remove":
            return comms.remove_contact(g("name")), DONE
        return comms.list_contacts(), INFO

    if name == "send_message":
        brain.on_status("Waiting for your OK...")
        if g("channel") == "email":
            return comms.send_email(g("to"), g("subject") or "(no subject)", a.get("message") or ""), DONE
        return comms.send_whatsapp(g("to"), a.get("message") or ""), DONE

    if name == "check_email":
        brain.on_status("Checking your email...")
        return comms.check_email(a.get("count") or 5, a.get("unread_only", True) is not False), INFO

    if name == "reminders":
        if act == "set":
            return reminders.add(g("text"), when=g("when")), DONE
        if act == "timer":
            return reminders.add(g("text") or "Timer finished", minutes=a.get("minutes") or 0), DONE
        if act == "cancel":
            return reminders.cancel(g("text")), DONE
        return reminders.list_all(), INFO

    if name == "create_powerpoint":
        return brain.make_presentation(g("topic")), DONE

    if name == "run_task":
        return brain.run_task(g("task")), DONE

    return f"Unknown tool {name} / action {act}.", DONE


def pause_between(name: str, a: dict) -> None:
    """Gives an app time to open before the next step types into it."""
    if name == "apps" and a.get("action") == "open":
        time.sleep(2.0)
    elif name in ("web",) and a.get("action") in ("open_url", "google", "youtube"):
        time.sleep(1.5)

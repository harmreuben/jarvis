"""Checks that everything JARVIS needs works on this PC. Run with check_setup.bat."""
import os
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

failures = []


def check(name, func, required=True):
    try:
        detail = func()
        print(f"  OK      {name}" + (f" - {detail}" if detail else ""))
    except Exception as e:
        tag = "FAILED " if required else "WARNING"
        print(f"  {tag} {name} - {e}")
        if os.environ.get("JARVIS_DEBUG"):
            traceback.print_exc()
        if required:
            failures.append(name)


def python_version():
    v = sys.version_info
    if (v.major, v.minor) != (3, 12):
        raise RuntimeError(f"Python {v.major}.{v.minor} found, 3.12 is required")
    return sys.version.split()[0]


def imports():
    import cv2, easyocr, eel, edge_tts, groq, pptx, pyautogui, pygame, pyperclip, ddgs, docx, send2trash, psutil  # noqa: F401
    if sys.platform == "win32":
        import pygetwindow  # noqa: F401
    return "all packages load"


brain_holder = {}


def groq_key():
    from backend.core.brain import Brain
    b = Brain()
    b.connect()
    brain_holder["b"] = b
    return f"chat model {b.llm_model}, vision model {b.vision_model or 'none'}"


def groq_reply():
    b = brain_holder.get("b")
    if not b:
        raise RuntimeError("skipped because the API key check failed")
    reply = b.complete([{"role": "user", "content": "Reply with exactly: JARVIS online"}], max_tokens=20, temperature=0)
    if not reply:
        raise RuntimeError("empty reply")
    import json
    from backend.core import tools
    resp = b._create(messages=[{"role": "system", "content": b._system()}, {"role": "user", "content": "open notepad"}],
                     tools=tools.TOOLS, tool_choice="auto", max_tokens=200, temperature=0)
    calls = resp.choices[0].message.tool_calls or []
    picked = [(c.function.name, json.loads(c.function.arguments or "{}").get("action")) for c in calls]
    if ("apps", "open") not in picked:
        raise RuntimeError(f"tool calling returned {picked or 'no tool'} instead of opening the app")
    return f'model says "{reply[:40]}", PC control (tool calling) works'


def web_search():
    from ddgs import DDGS
    results = DDGS().text("Python programming language", max_results=3)
    if not results:
        raise RuntimeError("no results")
    return f"{len(results)} results"


def online_voice():
    import asyncio
    import edge_tts
    path = os.path.join(tempfile.gettempdir(), "jarvis_voice_test.mp3")
    asyncio.run(edge_tts.Communicate("JARVIS online.", "en-GB-RyanNeural").save(path))
    size = os.path.getsize(path)
    os.remove(path)
    if size == 0:
        raise RuntimeError("no audio returned")
    return "Microsoft neural voice reachable"


def speakers():
    from backend.core.voice import speak
    if not speak("JARVIS setup check. If you can hear this, sound works."):
        raise RuntimeError("no voice could be played (see [voice] messages above)")
    return "played a test sentence - you should have heard it"


def browser():
    import eel.chrome
    if eel.chrome.find_path():
        return "Google Chrome found (JARVIS opens in Chrome)"
    if sys.platform == "win32":
        return "Chrome not found - JARVIS will open in Microsoft Edge"
    raise RuntimeError("no Chrome/Edge found")


def email_login():
    from backend.core import comms
    addr, password, servers = comms._mail_settings()
    if not addr:
        return "not set up (optional - add it in Settings to read/send email)"
    if not servers:
        raise RuntimeError(f"I don't know the mail servers for {addr.split('@')[-1]}")
    import imaplib
    imap = imaplib.IMAP4_SSL(servers[0], timeout=20)
    try:
        imap.login(addr, password)
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return f"logged in to {addr}"


def webcam():
    from backend.core.actions import capture_camera_image
    capture_camera_image()
    return "camera works"


def screen_capture():
    import pyautogui
    img = pyautogui.screenshot()
    return f"{img.size[0]}x{img.size[1]}"


if __name__ == "__main__":
    print("\nJARVIS setup check\n")
    check("Python 3.12", python_version)
    check("Python packages", imports)
    check("Groq API key", groq_key)
    check("Groq AI reply", groq_reply)
    check("Web search", web_search, required=False)
    check("Online voice", online_voice, required=False)
    check("Speakers", speakers, required=False)
    check("Browser for the JARVIS window", browser)
    check("Screen capture", screen_capture, required=False)
    check("Webcam", webcam, required=False)
    check("Email", email_login, required=False)
    print()
    if failures:
        print("FAILED: " + ", ".join(failures) + ". JARVIS will not work properly until this is fixed.")
        sys.exit(1)
    print("All required checks passed. WARNING lines are optional features.")

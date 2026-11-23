"""Things JARVIS can do on the Windows PC. Heavy libraries are imported inside functions so startup stays fast."""
import base64
import io
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import webbrowser
from datetime import datetime

IS_WINDOWS = sys.platform == "win32"
PICTURES_DIR = os.path.join(os.path.expanduser("~"), "Pictures", "JARVIS")

# Common apps that can be started directly; anything else is opened through Start-menu search.
KNOWN_APPS = {
    "notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint",
    "command prompt": "cmd", "cmd": "cmd", "terminal": "wt", "windows terminal": "wt",
    "powershell": "powershell", "file explorer": "explorer", "explorer": "explorer",
    "files": "explorer", "task manager": "taskmgr", "settings": "ms-settings:",
    "control panel": "control", "snipping tool": "snippingtool", "edge": "msedge",
    "microsoft edge": "msedge", "chrome": "chrome", "google chrome": "chrome",
    "word": "winword", "microsoft word": "winword", "excel": "excel",
    "microsoft excel": "excel", "powerpoint": "powerpnt", "microsoft powerpoint": "powerpnt",
    "camera": "microsoft.windows.camera:", "store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:", "spotify": "spotify:",
}


def _start(target: str) -> None:
    if IS_WINDOWS:
        subprocess.Popen(f'start "" "{target}"', shell=True)
    else:
        subprocess.Popen(["xdg-open", target])


def open_app(name: str) -> str:
    key = name.lower().strip().removesuffix(".exe")
    if key in KNOWN_APPS:
        _start(KNOWN_APPS[key])
        return f"Opening {name}."
    import pyautogui
    pyautogui.press("win")
    time.sleep(1.0)
    pyautogui.write(name, interval=0.03)
    time.sleep(1.2)
    pyautogui.press("enter")
    return f"Opening {name}."


def open_website(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opening {urllib.parse.urlparse(url).netloc or url}."


def play_youtube(query: str) -> str:
    import requests
    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    try:
        html = requests.get(search_url, timeout=10, headers={"Accept-Language": "en-US,en;q=0.9"}).text
        match = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
    except Exception:
        match = None
    webbrowser.open(f"https://www.youtube.com/watch?v={match.group(1)}" if match else search_url)
    return f"Playing {query} on YouTube." if match else f"Here are the YouTube results for {query}."


def type_text(text: str) -> str:
    import pyautogui
    import pyperclip
    previous = None
    try:
        previous = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(text)  # paste instead of typing so any language/symbol works
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)
    if previous is not None:
        try:
            pyperclip.copy(previous)
        except Exception:
            pass
    return "Done."


def click_on_screen(label: str) -> str:
    from backend.modules.ocr.ocroff import ocr_off  # loads EasyOCR (downloads its model on first use)
    result = ocr_off(label, double_click=False)
    if result and result.lower().startswith("ocr"):
        return f"Clicked {label}."
    return f"I couldn't find '{label}' on the screen."


def take_screenshot() -> str:
    import pyautogui
    os.makedirs(PICTURES_DIR, exist_ok=True)
    path = os.path.join(PICTURES_DIR, f"screenshot {datetime.now():%Y-%m-%d %H%M%S}.png")
    pyautogui.screenshot().save(path)
    return path


def _to_data_url(pil_image, max_side: int = 1280) -> str:
    img = pil_image.convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def capture_screen_image() -> str:
    import pyautogui
    return _to_data_url(pyautogui.screenshot())


def capture_camera_image() -> str:
    import cv2
    from PIL import Image
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if IS_WINDOWS else cv2.VideoCapture(0)
    try:
        if not cap.isOpened():
            raise RuntimeError("I couldn't open the webcam. Check that a camera is connected and allowed in Windows privacy settings.")
        frame = None
        for _ in range(10):  # let auto-exposure settle
            ok, f = cap.read()
            if ok:
                frame = f
            time.sleep(0.05)
        if frame is None:
            raise RuntimeError("The webcam didn't return an image.")
    finally:
        cap.release()
    return _to_data_url(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))


def system_setting(setting: str) -> str:
    s = setting.lower().strip()
    if s in ("dark_mode", "light_mode"):
        if not IS_WINDOWS:
            return "Theme switching only works on Windows."
        from TOOLS.SYSTEM_SETTINGS.system_theme import WindowsThemeManager
        WindowsThemeManager().set_theme(0 if s == "dark_mode" else 1)
        return "Dark mode enabled." if s == "dark_mode" else "Light mode enabled."
    if s in ("taskbar_left", "taskbar_center"):
        if not IS_WINDOWS:
            return "Taskbar settings only work on Windows."
        from TOOLS.SYSTEM_SETTINGS.taskbar import TaskbarCustomizer
        TaskbarCustomizer().set_alignment(0 if s == "taskbar_left" else 1)
        return "Taskbar moved to the left." if s == "taskbar_left" else "Taskbar centered."
    if s in ("volume_up", "volume_down", "mute"):
        import pyautogui
        if s == "mute":
            pyautogui.press("volumemute")
            return "Toggled mute."
        pyautogui.press("volumeup" if s == "volume_up" else "volumedown", presses=5, interval=0.03)
        return "Volume up." if s == "volume_up" else "Volume down."
    if s == "lock_pc":
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return "Locking the PC."
        return "Locking only works on Windows."
    return f"I don't know how to change the setting '{setting}'."


def confirm(title: str, message: str) -> bool:
    """Shows a Yes/No box on top of everything. Used before anything risky. Default button is No."""
    if IS_WINDOWS:
        import ctypes
        MB_YESNO, MB_ICONWARNING, MB_DEFBUTTON2, MB_TOPMOST, MB_SETFOREGROUND = 0x4, 0x30, 0x100, 0x40000, 0x10000
        return ctypes.windll.user32.MessageBoxW(
            None, message, "JARVIS - " + title,
            MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 | MB_TOPMOST | MB_SETFOREGROUND) == 6
    import pyautogui
    return pyautogui.confirm(text=message, title="JARVIS - " + title, buttons=["Yes", "No"]) == "Yes"


def confirm_run(code: str, script_path: str) -> bool:
    """Asks the user before running AI-written code. Nothing runs without a 'Yes'."""
    preview = "\n".join(code.splitlines()[:30])
    if len(code.splitlines()) > 30:
        preview += "\n..."
    return confirm("confirm task", "JARVIS wants to run this Python code on your PC:\n\n" + preview +
                   f"\n\nFull script: {script_path}\n\nRun it?")


def run_python_task(code: str, timeout: int = 300):
    """Saves the code to a file, asks for confirmation, runs it in a separate process.
    Returns (ran, returncode, output)."""
    folder = os.path.join(tempfile.gettempdir(), "jarvis_tasks")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"task_{datetime.now():%Y%m%d_%H%M%S}.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    if not confirm_run(code, path):
        return False, None, ""
    try:
        proc = subprocess.run([sys.executable, path], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, cwd=os.path.expanduser("~"),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True, proc.returncode, (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
    except subprocess.TimeoutExpired:
        return True, -1, f"The task was stopped after {timeout} seconds."


# ======================= PC control =======================
def _powershell(script: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _find_windows(name: str):
    import pygetwindow
    name = name.lower().strip()
    wins = [w for w in pygetwindow.getAllWindows() if w.title and name in w.title.lower()]
    return sorted(wins, key=lambda w: (not w.visible if hasattr(w, "visible") else 0, len(w.title)))


def _activate(win) -> None:
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
    except Exception:
        # Windows sometimes refuses focus changes; minimizing and restoring brings it forward anyway.
        try:
            win.minimize()
            win.restore()
        except Exception:
            pass


PROCESS_NAMES = {  # spoken name -> process image name, for apps whose window title doesn't contain their name
    "chrome": "chrome.exe", "google chrome": "chrome.exe", "edge": "msedge.exe", "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe", "notepad": "notepad.exe", "word": "WINWORD.EXE", "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE", "spotify": "Spotify.exe", "vlc": "vlc.exe", "teams": "ms-teams.exe",
    "discord": "Discord.exe", "whatsapp": "WhatsApp.exe", "telegram": "Telegram.exe", "zoom": "Zoom.exe",
    "visual studio code": "Code.exe", "vs code": "Code.exe", "vscode": "Code.exe", "calculator": "CalculatorApp.exe",
    "paint": "mspaint.exe", "file explorer": "explorer.exe", "steam": "steam.exe", "obs": "obs64.exe",
}


def close_app(name: str) -> str:
    if not IS_WINDOWS:
        return "Closing apps only works on Windows."
    wins = _find_windows(name)
    if wins:
        for w in wins:
            try:
                w.close()  # polite close: the app can still ask to save unsaved work
            except Exception:
                pass
        return f"Closed {name}."
    exe = PROCESS_NAMES.get(name.lower().strip())
    if exe and exe.lower() != "explorer.exe":
        r = subprocess.run(["taskkill", "/IM", exe], capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0:
            return f"Closed {name}."
    return f"I couldn't find an open window called {name}."


def window_control(action: str, name: str = "") -> str:
    import pyautogui
    if action == "minimize_all":
        pyautogui.hotkey("win", "d")
        return "Showing the desktop."
    if action == "next_window":
        pyautogui.hotkey("alt", "tab")
        return "Switched window."
    if not IS_WINDOWS:
        return "Window control only works on Windows."
    if not name:
        import pygetwindow
        win = pygetwindow.getActiveWindow()
        if not win:
            return "There's no active window."
        wins = [win]
    else:
        wins = _find_windows(name)
    if not wins:
        return f"I couldn't find a window called {name}."
    w = wins[0]
    if action == "switch":
        _activate(w)
        return f"Switched to {w.title[:60]}."
    if action == "minimize":
        w.minimize()
        return "Minimized."
    if action == "maximize":
        _activate(w)
        w.maximize()
        return "Maximized."
    if action == "close":
        return close_app(name or w.title)
    return f"Unknown window action {action}."


def press_keys(keys: str) -> str:
    """'ctrl+s', 'alt+tab', 'enter', 'win+e', 'ctrl+shift+esc' ..."""
    import pyautogui
    aliases = {"control": "ctrl", "windows": "win", "escape": "esc", "return": "enter", "del": "delete",
               "page down": "pagedown", "page up": "pageup", "arrow up": "up", "arrow down": "down",
               "arrow left": "left", "arrow right": "right", "spacebar": "space"}
    combo = [aliases.get(k.strip().lower(), k.strip().lower()) for k in re.split(r"\s*\+\s*", keys.strip()) if k.strip()]
    bad = [k for k in combo if k not in pyautogui.KEYBOARD_KEYS]
    if not combo or bad:
        return f"I don't know the key {', '.join(bad) or keys}."
    if len(combo) == 1:
        pyautogui.press(combo[0])
    else:
        pyautogui.hotkey(*combo)
    return "Done."


def scroll(direction: str, amount: int = 5) -> str:
    import pyautogui
    amount = max(1, min(int(amount or 5), 50))
    pyautogui.scroll(amount * 120 if direction == "up" else -amount * 120)
    return "Scrolled."


def media(action: str, level=None) -> str:
    import pyautogui
    keys = {"play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack", "stop": "stop", "mute": "volumemute"}
    if action in keys:
        pyautogui.press(keys[action])
        return {"play_pause": "Done.", "next": "Next track.", "previous": "Previous track.", "stop": "Stopped.",
                "mute": "Toggled mute."}[action]
    if action in ("volume_up", "volume_down"):
        pyautogui.press("volumeup" if action == "volume_up" else "volumedown", presses=5, interval=0.02)
        return "Volume up." if action == "volume_up" else "Volume down."
    if action == "volume_set":
        try:
            level = max(0, min(100, int(float(level))))
        except (TypeError, ValueError):
            return "What volume level, from 0 to 100?"
        # Each volume key press moves Windows volume by 2%: go to zero, then up to the level.
        pyautogui.press("volumedown", presses=50, interval=0.005)
        pyautogui.press("volumeup", presses=round(level / 2), interval=0.005)
        return f"Volume set to {level} percent."
    return f"Unknown media action {action}."


def brightness(action: str, level=None) -> str:
    if not IS_WINDOWS:
        return "Brightness control only works on Windows."
    cur = _powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Select-Object -First 1).CurrentBrightness")
    try:
        current = int(cur.stdout.strip())
    except ValueError:
        return "I can't change the brightness of this screen (that usually only works on laptop screens)."
    if action == "up":
        target = min(100, current + 20)
    elif action == "down":
        target = max(0, current - 20)
    else:
        try:
            target = max(0, min(100, int(float(level))))
        except (TypeError, ValueError):
            return "What brightness level, from 0 to 100?"
    r = _powershell("Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
                    f"Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness={target}}} | Out-Null")
    if r.returncode != 0:
        return "I couldn't change the brightness on this screen."
    return f"Brightness set to {target} percent."


def power(action: str) -> str:
    if not IS_WINDOWS:
        return "Power control only works on Windows."
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if action == "lock":
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return "Locking the PC."
    if action == "cancel_shutdown":
        r = subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=flags)
        return "Shutdown cancelled." if r.returncode == 0 else "There was no shutdown scheduled."
    labels = {"shutdown": "shut down", "restart": "restart", "sleep": "go to sleep", "sign_out": "sign out"}
    if action not in labels:
        return f"Unknown power action {action}."
    if not confirm("confirm", f"Do you want the PC to {labels[action]} now?\n\nSave your work first."):
        return "Okay, cancelled."
    if action == "shutdown":
        subprocess.run(["shutdown", "/s", "/t", "15"], creationflags=flags)
        return "Shutting down in 15 seconds. Say 'cancel shutdown' to stop it."
    if action == "restart":
        subprocess.run(["shutdown", "/r", "/t", "15"], creationflags=flags)
        return "Restarting in 15 seconds. Say 'cancel shutdown' to stop it."
    if action == "sign_out":
        subprocess.run(["shutdown", "/l"], creationflags=flags)
        return "Signing out."
    _powershell("Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false) | Out-Null")
    return "Going to sleep."


SETTINGS_PAGES = {
    "wifi": "ms-settings:network-wifi", "bluetooth": "ms-settings:bluetooth", "display": "ms-settings:display",
    "sound": "ms-settings:sound", "network": "ms-settings:network", "battery": "ms-settings:batterysaver",
    "apps": "ms-settings:appsfeatures", "updates": "ms-settings:windowsupdate", "privacy": "ms-settings:privacy",
    "notifications": "ms-settings:notifications", "personalization": "ms-settings:personalization",
    "storage": "ms-settings:storagesense", "mouse": "ms-settings:mousetouchpad", "keyboard": "ms-settings:typing",
    "default_apps": "ms-settings:defaultapps", "power": "ms-settings:powersleep", "accounts": "ms-settings:yourinfo",
    "home": "ms-settings:",
}


def open_settings_page(page: str) -> str:
    target = SETTINGS_PAGES.get((page or "home").lower().replace(" ", "_").replace("-", ""), "ms-settings:")
    _start(target)
    return f"Opening {page or 'Settings'} settings."


def system_info() -> str:
    import platform
    import socket
    import psutil
    parts = [f"CPU {psutil.cpu_percent(interval=0.3):.0f}%",
             f"memory {psutil.virtual_memory().percent:.0f}% used of {psutil.virtual_memory().total / 2**30:.0f} GB"]
    b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if b is not None:
        parts.append(f"battery {b.percent:.0f}% ({'charging' if b.power_plugged else 'on battery'})")
    home = os.path.splitdrive(os.path.expanduser("~"))[0] + os.sep if IS_WINDOWS else "/"
    d = psutil.disk_usage(home)
    parts.append(f"disk {home} {d.free / 2**30:.0f} GB free of {d.total / 2**30:.0f} GB")
    up = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
    parts.append(f"up for {up.days}d {up.seconds // 3600}h {(up.seconds // 60) % 60}m")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        parts.append(f"local IP {s.getsockname()[0]}")
        s.close()
    except OSError:
        parts.append("no network connection")
    parts.append(f"{platform.system()} {platform.release()}")
    return "; ".join(parts)
